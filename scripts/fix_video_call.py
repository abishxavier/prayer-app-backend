# 1. Update call_screen.dart
path_call = 'd:/prayer_app/flutter_application_1/lib/screens/call_screen.dart'
with open(path_call, 'r', encoding='utf-8') as f:
    call_content = f.read()

# Update _getVideoController with useAndroidSurfaceView: true and RenderModeType.renderModeHidden
target_get_ctrl = """  VideoViewController? _getVideoController(int uid) {
    if (_engine == null) return null;
    try {
      if (uid == 0) {
        _localVideoController ??= VideoViewController(
          rtcEngine: _engine!,
          canvas: const VideoCanvas(uid: 0),
        );
        return _localVideoController;
      } else {
        if (!_remoteVideoControllers.containsKey(uid) || _remoteVideoControllers[uid] == null) {
          _remoteVideoControllers[uid] = VideoViewController.remote(
            rtcEngine: _engine!,
            canvas: VideoCanvas(uid: uid),
            connection: RtcConnection(
              channelId: _joinedChannelId.isNotEmpty ? _joinedChannelId : _effectiveChannelName,
            ),
          );
        }
        return _remoteVideoControllers[uid];
      }
    } catch (e) {
      debugPrint('Error getting VideoViewController for uid $uid: $e');
      return null;
    }
  }"""

replacement_get_ctrl = """  VideoViewController? _getVideoController(int uid) {
    if (_engine == null) return null;
    try {
      if (uid == 0) {
        _localVideoController ??= VideoViewController(
          rtcEngine: _engine!,
          canvas: const VideoCanvas(
            uid: 0,
            renderMode: RenderModeType.renderModeHidden,
            mirrorMode: VideoMirrorModeType.videoMirrorModeAuto,
          ),
          useAndroidSurfaceView: true,
        );
        return _localVideoController;
      } else {
        if (!_remoteVideoControllers.containsKey(uid) || _remoteVideoControllers[uid] == null) {
          _remoteVideoControllers[uid] = VideoViewController.remote(
            rtcEngine: _engine!,
            canvas: VideoCanvas(
              uid: uid,
              renderMode: RenderModeType.renderModeHidden,
            ),
            connection: RtcConnection(
              channelId: _joinedChannelId.isNotEmpty ? _joinedChannelId : _effectiveChannelName,
            ),
            useAndroidSurfaceView: true,
          );
        }
        return _remoteVideoControllers[uid];
      }
    } catch (e) {
      debugPrint('Error getting VideoViewController for uid $uid: $e');
      return null;
    }
  }"""

if target_get_ctrl in call_content:
    call_content = call_content.replace(target_get_ctrl, replacement_get_ctrl, 1)
    print("Updated _getVideoController with useAndroidSurfaceView: true!")
else:
    print("Warning: target_get_ctrl not found!")

# Update _toggleLocalVideo
target_toggle_video = """  Future<void> _toggleLocalVideo() async {
    if (_engine != null) {
      final newVideoOff = !_isVideoOff;
      try {
        await _engine!.muteLocalVideoStream(newVideoOff);
      } catch (e) {
        debugPrint('Video toggle error: $e');
      }
      if (mounted) setState(() => _isVideoOff = newVideoOff);
      CallPopPlayerManager.instance.updateVideoStatus(newVideoOff);
    }
  }"""

replacement_toggle_video = """  Future<void> _toggleLocalVideo() async {
    if (_engine != null) {
      final newVideoOff = !_isVideoOff;
      try {
        await _engine!.muteLocalVideoStream(newVideoOff);
        await _engine!.enableLocalVideo(!newVideoOff);
        if (!newVideoOff) {
          await _engine!.startPreview();
        } else {
          await _engine!.stopPreview();
        }
      } catch (e) {
        debugPrint('Video toggle error: $e');
      }
      if (mounted) setState(() => _isVideoOff = newVideoOff);
      CallPopPlayerManager.instance.updateVideoStatus(newVideoOff);
    }
  }"""

if target_toggle_video in call_content:
    call_content = call_content.replace(target_toggle_video, replacement_toggle_video, 1)
    print("Updated _toggleLocalVideo with enableLocalVideo & startPreview!")
else:
    print("Warning: target_toggle_video not found!")

# Update onUserJoined to un-mute video by default
target_on_user_joined = """          onUserJoined: (RtcConnection connection, int remoteUid, int elapsed) {
            debugPrint("Remote participant $remoteUid joined call $channelId");
            if (mounted) {
              setState(() {
                if (!_remoteUids.contains(remoteUid)) {
                  _remoteUids.add(remoteUid);
                }
              });
            }"""

replacement_on_user_joined = """          onUserJoined: (RtcConnection connection, int remoteUid, int elapsed) {
            debugPrint("Remote participant $remoteUid joined call $channelId");
            if (mounted) {
              setState(() {
                if (!_remoteUids.contains(remoteUid)) {
                  _remoteUids.add(remoteUid);
                  _remoteVideoMuted[remoteUid] = false;
                  _remoteAudioMuted[remoteUid] = false;
                }
              });
            }"""

if target_on_user_joined in call_content:
    call_content = call_content.replace(target_on_user_joined, replacement_on_user_joined, 1)
    print("Updated onUserJoined to un-mute video by default!")
else:
    print("Warning: target_on_user_joined not found!")

# Update _renderParticipantTile isVideoMuted default
call_content = call_content.replace(
    "final bool isVideoMuted = isLocal ? _isVideoOff : (_remoteVideoMuted[uid] ?? true);",
    "final bool isVideoMuted = isLocal ? _isVideoOff : (_remoteVideoMuted[uid] ?? false);"
)

with open(path_call, 'w', encoding='utf-8') as f:
    f.write(call_content)
print("Updated call_screen.dart video settings!")

# 2. Update pre_join_screen.dart with transition delay
path_pre = 'd:/prayer_app/flutter_application_1/lib/screens/pre_join_screen.dart'
with open(path_pre, 'r', encoding='utf-8') as f:
    pre_content = f.read()

target_pre_nav = """    try {
      await _engine?.stopPreview();
      await _engine?.release();
      _engine = null;
    } catch (_) {}

    if (!mounted) return;

    Navigator.of(context).pushReplacement("""

replacement_pre_nav = """    try {
      await _engine?.stopPreview();
      await _engine?.release();
      _engine = null;
    } catch (_) {}

    if (!mounted) return;
    await Future.delayed(const Duration(milliseconds: 250));
    if (!mounted) return;

    Navigator.of(context).pushReplacement("""

if target_pre_nav in pre_content:
    pre_content = pre_content.replace(target_pre_nav, replacement_pre_nav, 1)
    print("Updated pre_join_screen.dart with transition delay!")
    with open(path_pre, 'w', encoding='utf-8') as f:
        f.write(pre_content)
else:
    print("Warning: target_pre_nav not found!")
