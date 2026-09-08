path = 'd:/prayer_app/flutter_application_1/lib/screens/call_screen.dart'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target_sync = """    final list = <Map<String, dynamic>>[
      {
        'name': _myUserName.isNotEmpty ? _myUserName : 'You',
        'isMuted': _isMuted,
        'uid': 0,
      }
    ];
    for (final uid in _remoteUids) {
      list.add({
        'name': _remoteNames[uid] ?? 'User $uid',
        'isMuted': _remoteAudioMuted[uid] ?? false,
        'uid': uid,
      });
    }"""

replacement_sync = """    final list = <Map<String, dynamic>>[
      {
        'name': _myUserName.isNotEmpty ? _myUserName : 'You',
        'isMuted': _isMuted,
        'uid': 0,
        'photo': _myPhotoUrl.isNotEmpty ? _myPhotoUrl : null,
      }
    ];
    for (final uid in _remoteUids) {
      list.add({
        'name': _remoteNames[uid] ?? 'User $uid',
        'isMuted': _remoteAudioMuted[uid] ?? false,
        'uid': uid,
        'photo': _remotePhotos[uid],
      });
    }"""

if target_sync in content:
    content = content.replace(target_sync, replacement_sync, 1)
    print("Replaced target_sync successfully!")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
else:
    print("Warning: target_sync not found!")
