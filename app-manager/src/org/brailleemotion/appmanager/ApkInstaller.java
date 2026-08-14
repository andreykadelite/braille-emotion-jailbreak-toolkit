package org.brailleemotion.appmanager;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.os.Build;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

final class ApkInstaller {
    private static final int BUFFER_SIZE = 64 * 1024;
    private static final long RESERVED_FREE_BYTES = 8L * 1024L * 1024L;

    private ApkInstaller() {
    }

    static void clearPrepared(Context context) {
        File destination = ApkInstallFileProvider.getPreparedApkFile(context);
        File cacheDirectory = destination.getParentFile();
        File temporary = cacheDirectory == null
                ? null
                : new File(cacheDirectory, "pending-install.tmp");
        if (temporary != null && temporary.isFile()) {
            temporary.delete();
        }
        if (destination.isFile()) {
            destination.delete();
        }
    }

    static File prepare(Context context, ApkEntry entry) throws IOException {
        File downloadDirectory = android.os.Environment.getExternalStoragePublicDirectory(
                android.os.Environment.DIRECTORY_DOWNLOADS);
        File source = ApkRepository.requireDirectDownloadChild(
                downloadDirectory,
                entry.file);
        if (!source.isFile() || !source.canRead() || source.length() <= 0) {
            throw new IOException("APK cannot be read");
        }

        File destination = ApkInstallFileProvider.getPreparedApkFile(context);
        File cacheDirectory = destination.getParentFile();
        if (cacheDirectory == null
                || (!cacheDirectory.isDirectory() && !cacheDirectory.mkdirs())) {
            throw new IOException("Cannot create the APK cache directory");
        }
        long usableSpace = cacheDirectory.getUsableSpace();
        if (usableSpace > 0 && source.length() + RESERVED_FREE_BYTES > usableSpace) {
            throw new IOException("Not enough free space to prepare the APK");
        }

        File temporary = new File(cacheDirectory, "pending-install.tmp");
        if (temporary.exists() && !temporary.delete()) {
            throw new IOException("Cannot replace the temporary APK");
        }

        long copied = 0;
        try (InputStream input = new FileInputStream(source);
             FileOutputStream output = new FileOutputStream(temporary)) {
            byte[] buffer = new byte[BUFFER_SIZE];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
                copied += count;
            }
            output.flush();
            output.getFD().sync();
        } catch (IOException exception) {
            temporary.delete();
            throw exception;
        }

        if (copied != source.length()) {
            temporary.delete();
            throw new IOException("The APK copy is incomplete");
        }
        if (destination.exists() && !destination.delete()) {
            temporary.delete();
            throw new IOException("Cannot replace the prepared APK");
        }
        if (!temporary.renameTo(destination)) {
            temporary.delete();
            throw new IOException("Cannot finalize the prepared APK");
        }

        PackageInfo preparedPackage = context.getPackageManager().getPackageArchiveInfo(
                destination.getAbsolutePath(),
                0);
        long preparedVersion = preparedPackage == null
                ? -1L
                : (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                        ? preparedPackage.getLongVersionCode()
                        : preparedPackage.versionCode);
        if (preparedPackage == null
                || !entry.packageName.equals(preparedPackage.packageName)
                || entry.versionCode != preparedVersion) {
            destination.delete();
            throw new IOException("APK identity changed while it was being prepared");
        }

        context.getSharedPreferences("apk_provider", Context.MODE_PRIVATE)
                .edit()
                .putString("display_name", entry.fileName)
                .apply();
        return destination;
    }
}
