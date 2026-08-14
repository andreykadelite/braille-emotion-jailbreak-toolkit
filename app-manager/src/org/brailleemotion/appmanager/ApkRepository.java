package org.brailleemotion.appmanager;

import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Environment;

import java.io.File;
import java.io.IOException;
import java.text.Collator;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

final class ApkRepository {
    private ApkRepository() {
    }

    static ScanResult scanDownloads(PackageManager packageManager) {
        File downloadDirectory = Environment.getExternalStoragePublicDirectory(
                Environment.DIRECTORY_DOWNLOADS);
        ArrayList<ApkEntry> entries = new ArrayList<ApkEntry>();
        int invalidApkCount = 0;

        File[] files;
        try {
            files = downloadDirectory.listFiles();
        } catch (SecurityException exception) {
            return new ScanResult(entries, 0, true, downloadDirectory);
        }
        if (files == null) {
            return new ScanResult(entries, 0, true, downloadDirectory);
        }

        for (File file : files) {
            if (file == null
                    || !file.isFile()
                    || !file.canRead()
                    || !file.getName().toLowerCase(Locale.US).endsWith(".apk")) {
                continue;
            }

            try {
                File canonicalFile = requireDirectDownloadChild(downloadDirectory, file);
                PackageInfo packageInfo = packageManager.getPackageArchiveInfo(
                        canonicalFile.getAbsolutePath(),
                        PackageManager.GET_ACTIVITIES);
                if (packageInfo == null
                        || packageInfo.packageName == null
                        || packageInfo.applicationInfo == null) {
                    invalidApkCount++;
                    continue;
                }

                ApplicationInfo applicationInfo = packageInfo.applicationInfo;
                applicationInfo.sourceDir = canonicalFile.getAbsolutePath();
                applicationInfo.publicSourceDir = canonicalFile.getAbsolutePath();
                CharSequence loadedLabel = applicationInfo.loadLabel(packageManager);
                String label = loadedLabel == null
                        ? packageInfo.packageName
                        : loadedLabel.toString().trim();
                if (label.length() == 0) {
                    label = packageInfo.packageName;
                }

                String versionName = packageInfo.versionName == null
                        ? "—"
                        : packageInfo.versionName.trim();
                if (versionName.length() == 0) {
                    versionName = "—";
                }
                long versionCode = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                        ? packageInfo.getLongVersionCode()
                        : packageInfo.versionCode;
                entries.add(new ApkEntry(
                        canonicalFile,
                        label,
                        canonicalFile.getName(),
                        packageInfo.packageName,
                        versionName,
                        versionCode,
                        canonicalFile.length()));
            } catch (IOException | RuntimeException exception) {
                invalidApkCount++;
            }
        }

        final Collator collator = Collator.getInstance(new Locale("ru", "RU"));
        collator.setStrength(Collator.PRIMARY);
        Collections.sort(entries, new Comparator<ApkEntry>() {
            @Override
            public int compare(ApkEntry left, ApkEntry right) {
                int labelResult = collator.compare(left.label, right.label);
                if (labelResult != 0) {
                    return labelResult;
                }
                return left.fileName.compareToIgnoreCase(right.fileName);
            }
        });
        return new ScanResult(entries, invalidApkCount, false, downloadDirectory);
    }

    static File requireDirectDownloadChild(File downloadDirectory, File candidate)
            throws IOException {
        File canonicalDirectory = downloadDirectory.getCanonicalFile();
        File canonicalCandidate = candidate.getCanonicalFile();
        File parent = canonicalCandidate.getParentFile();
        if (parent == null || !parent.equals(canonicalDirectory)) {
            throw new IOException("APK is outside the Download directory");
        }
        return canonicalCandidate;
    }

    static final class ScanResult {
        final List<ApkEntry> entries;
        final int invalidApkCount;
        final boolean directoryUnavailable;
        final File downloadDirectory;

        ScanResult(
                List<ApkEntry> entries,
                int invalidApkCount,
                boolean directoryUnavailable,
                File downloadDirectory) {
            this.entries = entries;
            this.invalidApkCount = invalidApkCount;
            this.directoryUnavailable = directoryUnavailable;
            this.downloadDirectory = downloadDirectory;
        }
    }
}
