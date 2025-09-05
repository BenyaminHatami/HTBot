from django.contrib import admin
from .models import Symbol, Candle, PositionManager


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ('symbol',)
    search_fields = ('symbol',)
    ordering = ('symbol',)


@admin.register(Candle)
class CandleAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'open_time', 'interval', 'open', 'high', 'low', 'close', 'usdt_volume')
    list_filter = ('symbol', 'interval')
    search_fields = ('symbol__symbol', 'open_time')
    ordering = ('-open_time', 'symbol')
    list_per_page = 100

    fieldsets = (
        ('Identification', {
            'fields': ('symbol', 'open_time', 'interval')
        }),
        ('Price Data', {
            'fields': ('open', 'high', 'low', 'close')
        }),
        ('Volume Data', {
            'fields': ('base_volume', 'usdt_volume', 'quote_volume'),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['symbol', 'open_time', 'interval']
        return []

    def formatted_open_time(self, obj):
        import datetime
        return datetime.datetime.fromtimestamp(obj.open_time / 1000).strftime('%Y-%m-%d %H:%M:%S')

    formatted_open_time.short_description = 'Open Time'
    formatted_open_time.admin_order_field = 'open_time'


@admin.register(PositionManager)
class PositionManagerAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_position_active', 'timestamp_cursor', 'sl_order_price', 'created', 'updated')
    list_filter = ('is_position_active',)
    search_fields = ('remote_id',)
    ordering = ('-updated',)
    list_per_page = 50

    fieldsets = (
        ('API Credentials', {
            'fields': ('api_key', 'secret_key', 'api_passphrase'),
            'classes': ('collapse',),  # Collapsible to reduce visibility of sensitive data
        }),
        ('Position Details', {
            'fields': ('is_position_active', 'timestamp_cursor', 'remote_id'),
        }),
        ('Metadata', {
            'fields': ('created', 'updated', 'trace'),
            'classes': ('collapse',),
        }),
    )

    # Make sensitive fields read-only when editing an existing object to prevent accidental changes
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['api_key', 'secret_key', 'api_passphrase', 'created', 'updated']
        return ['created', 'updated']

    # Mask sensitive fields in the list view for security
    def get_api_key_display(self, obj):
        return '****' + obj.api_key[-4:] if obj.api_key else 'N/A'

    def get_secret_key_display(self, obj):
        return '****' + obj.secret_key[-4:] if obj.secret_key else 'N/A'

    def get_api_passphrase_display(self, obj):
        return '****' + obj.api_passphrase[-4:] if obj.api_passphrase else 'N/A'

    get_api_key_display.short_description = 'API Key'
    get_secret_key_display.short_description = 'Secret Key'
    get_api_passphrase_display.short_description = 'API Passphrase'

    # Optionally include these in list_display for a masked view
    # list_display = ('id', 'get_api_key_display', 'is_position_active', 'timestamp_cursor', 'created', 'updated')

    # Format timestamps for better readability
    def formatted_created(self, obj):
        return obj.created.strftime('%Y-%m-%d %H:%M:%S') if obj.created else 'N/A'

    def formatted_updated(self, obj):
        return obj.updated.strftime('%Y-%m-%d %H:%M:%S') if obj.updated else 'N/A'

    formatted_created.short_description = 'Created'
    formatted_created.admin_order_field = 'created'
    formatted_updated.short_description = 'Updated'
    formatted_updated.admin_order_field = 'updated'

    # Restrict access to sensitive fields based on user permissions (optional)
    def has_change_permission(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return False  # Only superusers can edit PositionManager instances
        return super().has_change_permission(request, obj)

    # Add custom actions (e.g., toggle position active status)
    actions = ['toggle_position_active']

    def toggle_position_active(self, request, queryset):
        for position in queryset:
            position.is_position_active = not position.is_position_active
            position.save()
        self.message_user(request, f"Updated position active status for {queryset.count()} position(s).")

    toggle_position_active.short_description = "Toggle position active status"
