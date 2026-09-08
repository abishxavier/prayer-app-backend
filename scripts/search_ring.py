with open('d:/prayer_app/flutter_application_1/lib/services/notification_service.dart', encoding='utf-8') as f:
    for idx, line in enumerate(f, 1):
        if any(k in line.lower() for k in ['ring', 'scheduled_call', 'ishost', 'is_host', 'host_id']):
            safe_line = line.strip().encode('ascii', 'replace').decode('ascii')
            print(f'{idx}: {safe_line[:100]}')
