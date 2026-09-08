path = 'd:/prayer_app/flutter_application_1/lib/widgets/call_pop_player.dart'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target_badge_call = '''                        // ── CENTER ROW: Participant 1 ("You"), Expand Center Icon, Participant 2 ("Xavier") ──
                        ValueListenableBuilder<List<Map<String, dynamic>>>(
                          valueListenable: CallPopPlayerManager.instance.participants,
                          builder: (context, participantsList, _) {
                            final list = participantsList.isNotEmpty
                                ? participantsList
                                : [
                                    {'name': 'You', 'isMuted': CallPopPlayerManager.instance.isMuted.value},
                                  ];

                            final first = list.first;
                            final second = list.length > 1
                                ? list[1]
                                : {
                                    'name': CallPopPlayerManager.instance.hostName ?? 'Xavier',
                                    'isMuted': true,
                                  };

                            return Row(
                              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                              children: [
                                // Participant 1: "You"
                                _buildParticipantBadge(
                                  first['name'] ?? 'You',
                                  isYou: true,
                                  isMuted: CallPopPlayerManager.instance.isMuted.value,
                                ),

                                // Center Expand / Fullscreen Button
                                GestureDetector(
                                  behavior: HitTestBehavior.opaque,
                                  onTap: () => CallPopPlayerManager.instance.expand(),
                                  child: Container(
                                    padding: const EdgeInsets.all(6),
                                    decoration: BoxDecoration(
                                      color: Colors.white.withAlpha(12),
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                    child: const Icon(
                                      Icons.crop_free,
                                      color: Colors.white,
                                      size: 22,
                                    ),
                                  ),
                                ),

                                // Participant 2: "Xavier"
                                _buildParticipantBadge(
                                  second['name'] ?? 'Xavier',
                                  isYou: false,
                                  isMuted: second['isMuted'] == true,
                                ),
                              ],
                            );
                          },
                        ),'''

replacement_badge_call = '''                        // ── CENTER ROW: Participant(s) and Center Expand Icon (No duplicate avatar) ──
                        ValueListenableBuilder<List<Map<String, dynamic>>>(
                          valueListenable: CallPopPlayerManager.instance.participants,
                          builder: (context, participantsList, _) {
                            final list = participantsList.isNotEmpty
                                ? participantsList
                                : [
                                    {'name': 'You', 'isMuted': CallPopPlayerManager.instance.isMuted.value},
                                  ];

                            final first = list.first;
                            final bool hasRemote = list.length > 1;
                            final second = hasRemote ? list[1] : null;

                            return Row(
                              mainAxisAlignment: hasRemote ? MainAxisAlignment.spaceEvenly : MainAxisAlignment.center,
                              children: [
                                // Participant 1: "You"
                                _buildParticipantBadge(
                                  first['name']?.toString() ?? 'You',
                                  photoUrl: first['photo']?.toString(),
                                  isYou: true,
                                  isMuted: CallPopPlayerManager.instance.isMuted.value,
                                ),

                                if (!hasRemote) const SizedBox(width: 14),

                                // Center Expand / Fullscreen Button
                                GestureDetector(
                                  behavior: HitTestBehavior.opaque,
                                  onTap: () => CallPopPlayerManager.instance.expand(),
                                  child: Container(
                                    padding: const EdgeInsets.all(7),
                                    decoration: BoxDecoration(
                                      color: Colors.white.withAlpha(15),
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                    child: const Icon(
                                      Icons.crop_free,
                                      color: Colors.white,
                                      size: 22,
                                    ),
                                  ),
                                ),

                                if (hasRemote && second != null) ...[
                                  // Participant 2: Remote
                                  _buildParticipantBadge(
                                    second['name']?.toString() ?? 'Participant',
                                    photoUrl: second['photo']?.toString(),
                                    isYou: false,
                                    isMuted: second['isMuted'] == true,
                                  ),
                                ],
                              ],
                            );
                          },
                        ),'''

target_def = '''  Widget _buildParticipantBadge(String name, {required bool isYou, required bool isMuted}) {
    final cleanName = name.trim();
    final firstLetter = cleanName.isNotEmpty ? cleanName[0].toUpperCase() : (isYou ? 'A' : 'X');

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: isYou
                      ? [const Color(0xFFD97706), const Color(0xFFEA580C)]
                      : [const Color(0xFF334155), const Color(0xFF475569)],
                ),
                border: Border.all(
                  color: Colors.white.withAlpha(35),
                  width: 1.2,
                ),
              ),
              child: Center(
                child: Text(
                  firstLetter,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  ),
                ),
              ),
            ),'''

replacement_def = '''  Widget _buildParticipantBadge(
    String name, {
    String? photoUrl,
    required bool isYou,
    required bool isMuted,
  }) {
    final cleanName = name.trim();
    final firstLetter = cleanName.isNotEmpty ? cleanName[0].toUpperCase() : (isYou ? 'Y' : 'P');
    final bool hasValidPhoto = photoUrl != null &&
        photoUrl.trim().isNotEmpty &&
        (photoUrl.startsWith('http://') || photoUrl.startsWith('https://'));

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: hasValidPhoto
                    ? null
                    : LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: isYou
                            ? [const Color(0xFFD97706), const Color(0xFFEA580C)]
                            : [const Color(0xFF334155), const Color(0xFF475569)],
                      ),
                border: Border.all(
                  color: Colors.white.withAlpha(35),
                  width: 1.2,
                ),
              ),
              child: hasValidPhoto
                  ? ClipOval(
                      child: Image.network(
                        photoUrl.trim(),
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => Center(
                          child: Text(
                            firstLetter,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 15,
                            ),
                          ),
                        ),
                      ),
                    )
                  : Center(
                      child: Text(
                        firstLetter,
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 15,
                        ),
                      ),
                    ),
            ),'''

if target_badge_call in content:
    content = content.replace(target_badge_call, replacement_badge_call, 1)
    print("Replaced badge call successfully!")
else:
    print("Warning: target_badge_call not found!")

if target_def in content:
    content = content.replace(target_def, replacement_def, 1)
    print("Replaced badge def successfully!")
else:
    print("Warning: target_def not found!")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated call_pop_player.dart!")
