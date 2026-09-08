with open('d:/prayer_app/flutter_application_1/lib/screens/call_screen.dart', encoding='utf-8') as f:
    for idx, line in enumerate(f, 1):
        if 'chat' in line.lower():
            if any(k in line.lower() for k in ['btn', 'button', 'action', 'item', 'onpressed', 'ontap', 'sheet', 'icon:']):
                safe_line = line.strip().encode('ascii', 'replace').decode('ascii')
                print(f'{idx}: {safe_line[:100]}')
