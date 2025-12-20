class Machine {
  final String id;
  final String username;
  final String ipAddress;
  final String os;
  final bool isOnline;
  final DateTime? lastSeen;

  Machine({
    required this.id,
    required this.username,
    required this.ipAddress,
    required this.os,
    this.isOnline = true,
    this.lastSeen,
  });

  factory Machine.fromJson(Map<String, dynamic> json) {
    final String ip = (json['host'] ?? '').toString();

    final String resolvedOs =
        (json['os'] != null && json['os'].toString().isNotEmpty)
            ? json['os'].toString()
            : 'unknown';

    final String resolvedUser =
        (json['user'] != null && json['user'].toString().isNotEmpty)
            ? json['user'].toString()
            : _fallbackUsername(resolvedOs, ip);

    return Machine(
      id: ip, // use IP as stable ID
      ipAddress: ip,
      username: resolvedUser,
      os: resolvedOs,
      isOnline: true,
      lastSeen: DateTime.now(),
    );
  }

  static String _fallbackUsername(String os, String ip) {
    if (os.startsWith('win')) return 'Windows Host';
    if (os.startsWith('lin')) return 'Linux Host';
    return 'Device $ip';
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'username': username,
      'ip_address': ipAddress,
      'os': os,
      'is_online': isOnline,
      'last_seen': lastSeen?.toIso8601String(),
    };
  }
}
