import 'package:lanfxplorer/core/constants/enums.dart';

class TransferTask {
  final String id;
  final List<String> files; // Changed from sourceFile to files
  final String destinationMachine;
  final TransferDirection direction;
  final TransferStatus status;
  final double progress;
  final DateTime createdAt;
  final DateTime? completedAt;
  final String? errorMessage;

  TransferTask({
    required this.id,
    required this.files,
    required this.destinationMachine,
    required this.direction,
    required this.status,
    required this.progress,
    required this.createdAt,
    this.completedAt,
    this.errorMessage,
  });

  factory TransferTask.fromJson(Map<String, dynamic> json) => TransferTask(
        id: json['id'] ?? '',
        files: List<String>.from(json['files'] ?? []),
        destinationMachine: json['destination_machine'] ?? '',
        direction: TransferDirection.values.firstWhere(
          (e) => e.name == json['direction'],
          orElse: () => TransferDirection.send,
        ),
        status: TransferStatus.values.firstWhere(
          (e) => e.name == json['status'],
          orElse: () => TransferStatus.pending,
        ),
        progress: (json['progress'] ?? 0).toDouble(),
        createdAt:
            DateTime.tryParse(json['created_at'] ?? '') ?? DateTime.now(),
        completedAt: json['completed_at'] != null
            ? DateTime.tryParse(json['completed_at'])
            : null,
        errorMessage: json['error_message'],
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'files': files,
        'destination_machine': destinationMachine,
        'direction': direction.name,
        'status': status.name,
        'progress': progress,
        'created_at': createdAt.toIso8601String(),
        'completed_at': completedAt?.toIso8601String(),
        'error_message': errorMessage,
      };

  TransferTask copyWith({
    String? id,
    List<String>? files,
    String? destinationMachine,
    TransferDirection? direction,
    TransferStatus? status,
    double? progress,
    DateTime? createdAt,
    DateTime? completedAt,
    String? errorMessage,
  }) {
    return TransferTask(
      id: id ?? this.id,
      files: files ?? this.files,
      destinationMachine: destinationMachine ?? this.destinationMachine,
      direction: direction ?? this.direction,
      status: status ?? this.status,
      progress: progress ?? this.progress,
      createdAt: createdAt ?? this.createdAt,
      completedAt: completedAt ?? this.completedAt,
      errorMessage: errorMessage ?? this.errorMessage,
    );
  }

  String get directionText =>
      direction == TransferDirection.send ? 'Sending' : 'Receiving';

  String get displayName =>
      files.isNotEmpty ? files.first.split('/').last : 'Unknown';
}
