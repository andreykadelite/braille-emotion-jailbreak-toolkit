package org.brailleemotion.appmanager;

import java.io.File;

final class ApkEntry {
    final File file;
    final String label;
    final String fileName;
    final String packageName;
    final String versionName;
    final long versionCode;
    final long sizeBytes;

    ApkEntry(
            File file,
            String label,
            String fileName,
            String packageName,
            String versionName,
            long versionCode,
            long sizeBytes) {
        this.file = file;
        this.label = label;
        this.fileName = fileName;
        this.packageName = packageName;
        this.versionName = versionName;
        this.versionCode = versionCode;
        this.sizeBytes = sizeBytes;
    }
}
