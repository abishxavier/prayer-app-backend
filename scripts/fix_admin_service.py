# 1. Update admin_service.dart
path_admin = 'd:/prayer_app/flutter_application_1/lib/services/admin_service.dart'
with open(path_admin, 'r', encoding='utf-8') as f:
    admin_content = f.read()

# Replace alwaysPrompt = true with alwaysPrompt = false
admin_content = admin_content.replace('bool alwaysPrompt = true,', 'bool alwaysPrompt = false,')

# Add remember checkbox and defaultRemember
old_defaults = """    final defaultHint = isTamilLang ? 'நிர்வாக கடவுச்சொல்' : 'Enter Admin Password';
    final cancelLabel = isTamilLang ? 'ரத்து' : 'Cancel';"""

new_defaults = """    final defaultHint = isTamilLang ? 'நிர்வாக கடவுச்சொல்' : 'Enter Admin Password';
    final defaultRemember = isTamilLang
        ? 'இந்த சாதனத்தில் திறந்தே வைக்கவும்'
        : 'Keep unlocked on this device';
    final cancelLabel = isTamilLang ? 'ரத்து' : 'Cancel';"""

admin_content = admin_content.replace(old_defaults, new_defaults)
admin_content = admin_content.replace('bool obscurePassword = true;', 'bool obscurePassword = true;\n    bool rememberDevice = true;')

old_text_field_end = """                    onSubmitted: (_) async {
                      final currentPass = await getAdminPassword();
                      final input = passwordController.text;
                      if (checkPassword(input, currentPass)) {
                        if (dialogCtx.mounted) Navigator.pop(dialogCtx, true);
                      } else {
                        setState(() => errorMessage = errText);
                      }
                    },
                  ),
                ],
              ),"""

new_text_field_end = """                    onSubmitted: (_) async {
                      final currentPass = await getAdminPassword();
                      final input = passwordController.text;
                      if (checkPassword(input, currentPass)) {
                        if (rememberDevice) await unlockAdmin();
                        if (dialogCtx.mounted) Navigator.pop(dialogCtx, true);
                      } else {
                        setState(() => errorMessage = errText);
                      }
                    },
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Checkbox(
                        value: rememberDevice,
                        activeColor: PrayerAppTheme.primary,
                        onChanged: (val) => setState(() => rememberDevice = val ?? true),
                      ),
                      Expanded(
                        child: Text(
                          defaultRemember,
                          style: TextStyle(fontSize: 12, color: isDark ? Colors.white60 : Colors.black54),
                        ),
                      ),
                    ],
                  ),
                ],
              ),"""

admin_content = admin_content.replace(old_text_field_end, new_text_field_end)

old_btn_action = """                    if (checkPassword(input, currentPass)) {
                      if (dialogCtx.mounted) Navigator.pop(dialogCtx, true);
                    }"""

new_btn_action = """                    if (checkPassword(input, currentPass)) {
                      if (rememberDevice) await unlockAdmin();
                      if (dialogCtx.mounted) Navigator.pop(dialogCtx, true);
                    }"""

admin_content = admin_content.replace(old_btn_action, new_btn_action)

with open(path_admin, 'w', encoding='utf-8') as f:
    f.write(admin_content)
print("Updated admin_service.dart with rememberDevice checkbox and alwaysPrompt=false!")

# 2. Update call_hub_screen.dart to use alwaysPrompt: false (so remember works)
path_hub = 'd:/prayer_app/flutter_application_1/lib/screens/call_hub_screen.dart'
with open(path_hub, 'r', encoding='utf-8') as f:
    hub_content = f.read()

hub_content = hub_content.replace('alwaysPrompt: true,', 'alwaysPrompt: false,')
with open(path_hub, 'w', encoding='utf-8') as f:
    f.write(hub_content)
print("Updated call_hub_screen.dart alwaysPrompt: false!")

# 3. Update main.dart to not lock admin on startup
path_main = 'd:/prayer_app/flutter_application_1/lib/main.dart'
with open(path_main, 'r', encoding='utf-8') as f:
    main_content = f.read()

main_content = main_content.replace("""  try {
    await AdminService.lockAdmin();
  } catch (_) {}
""", "")
with open(path_main, 'w', encoding='utf-8') as f:
    f.write(main_content)
print("Updated main.dart to preserve admin unlock status!")
