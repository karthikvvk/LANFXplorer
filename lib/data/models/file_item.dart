class FileItem {
  final String name;
  final String path;
  final bool isDirectory;
  final int? size;
  final DateTime? modified;
  final bool isSelected;

  FileItem({
    required this.name,
    required this.path,
    required this.isDirectory,
    this.size,
    this.modified,
    this.isSelected = false,
  });

  FileItem copyWith({
    String? name,
    String? path,
    bool? isDirectory,
    int? size,
    DateTime? modified,
    bool? isSelected,
  }) => FileItem(
    name: name ?? this.name,
    path: path ?? this.path,
    isDirectory: isDirectory ?? this.isDirectory,
    size: size ?? this.size,
    modified: modified ?? this.modified,
    isSelected: isSelected ?? this.isSelected,
  );

  factory FileItem.fromJson(Map<String, dynamic> json) => FileItem(
    name: json['name'] ?? '',
    path: json['path'] ?? '',
    isDirectory: json['is_directory'] ?? false,
    size: json['size'],
    modified: json['modified'] != null ? DateTime.tryParse(json['modified']) : null,
    isSelected: json['isSelected'] ?? false,
  );

  Map<String, dynamic> toJson() => {
    'name': name,
    'path': path,
    'is_directory': isDirectory,
    'size': size,
    'modified': modified?.toIso8601String(),
    'isSelected': isSelected,
  };
}