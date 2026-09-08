path = 'd:/prayer_app/flutter_application_1/lib/screens/call_screen.dart'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target_chat_btn = """                              // In-Meeting Chat Button (with unread badge)
                              Stack(
                                clipBehavior: Clip.none,
                                children: [
                                  _ControlButton(
                                    icon: Icons.chat_bubble_outline_rounded,
                                    label: 'Chat',
                                    color: const Color(0xFF3B82F6),
                                    isActive: false,
                                    onTap: _showChatSheet,
                                  ),
                                  if (_unreadChatCount > 0)
                                    Positioned(
                                      right: -2,
                                      top: -2,
                                      child: Container(
                                        padding: const EdgeInsets.all(5),
                                        decoration: const BoxDecoration(color: Color(0xFFEF4444), shape: BoxShape.circle),
                                        child: Text(
                                          '$_unreadChatCount',
                                          style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold),
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                              const SizedBox(width: 14),"""

if target_chat_btn in content:
    content = content.replace(target_chat_btn, "")
    print("Chat button removed from bottom bar!")
else:
    print("Warning: target_chat_btn not found!")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated call_screen.dart!")
