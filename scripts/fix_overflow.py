path = 'd:/prayer_app/flutter_application_1/lib/screens/call_hub_screen.dart'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if "'Host'}:" in line and "host_name" in line:
        print(f"Found at line {idx + 1}")
        # line idx-1 is Text(
        lines[idx-1] = ' ' * 54 + 'Expanded(\n' + ' ' * 56 + 'child: Text(\n'
        lines[idx] = '  ' + lines[idx]
        lines[idx+1] = ' ' * 58 + 'style: TextStyle(color: PrayerAppTheme.textSecondary, fontSize: 12),\n' + ' ' * 58 + 'overflow: TextOverflow.ellipsis,\n' + ' ' * 58 + 'maxLines: 1,\n'
        lines[idx+2] = ' ' * 56 + '),\n' + ' ' * 54 + '),\n'
        break

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("SUCCESS!")
