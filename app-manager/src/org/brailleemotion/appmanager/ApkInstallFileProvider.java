package org.brailleemotion.appmanager;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

public final class ApkInstallFileProvider extends ContentProvider {
    static final String AUTHORITY = "org.brailleemotion.appmanager.apkprovider";
    private static final String URI_PATH = "pending.apk";
    private static final String CACHE_DIRECTORY = "apk-installer";
    private static final String CACHE_FILE = "pending-install.apk";

    static Uri getPreparedApkUri() {
        return new Uri.Builder()
                .scheme("content")
                .authority(AUTHORITY)
                .appendPath(URI_PATH)
                .build();
    }

    static File getPreparedApkFile(android.content.Context context) {
        return new File(new File(context.getCacheDir(), CACHE_DIRECTORY), CACHE_FILE);
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public String getType(Uri uri) {
        requireSupportedUri(uri);
        return "application/vnd.android.package-archive";
    }

    @Override
    public Cursor query(
            Uri uri,
            String[] projection,
            String selection,
            String[] selectionArgs,
            String sortOrder) {
        requireSupportedUri(uri);
        File file;
        try {
            file = requirePreparedFile();
        } catch (FileNotFoundException exception) {
            throw new IllegalStateException("Prepared APK is unavailable", exception);
        }
        String displayName = getContext()
                .getSharedPreferences("apk_provider", 0)
                .getString("display_name", "application.apk");
        String[] requested = projection == null
                ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE}
                : projection;
        MatrixCursor cursor = new MatrixCursor(requested, 1);
        MatrixCursor.RowBuilder row = cursor.newRow();
        for (String column : requested) {
            if (OpenableColumns.DISPLAY_NAME.equals(column)) {
                row.add(displayName);
            } else if (OpenableColumns.SIZE.equals(column)) {
                row.add(file.length());
            } else {
                row.add(null);
            }
        }
        return cursor;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode)
            throws FileNotFoundException {
        requireSupportedUri(uri);
        if (!"r".equals(mode)) {
            throw new FileNotFoundException("The APK provider is read-only");
        }
        return ParcelFileDescriptor.open(
                requirePreparedFile(),
                ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("The APK provider is read-only");
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("The APK provider is read-only");
    }

    @Override
    public int update(
            Uri uri,
            ContentValues values,
            String selection,
            String[] selectionArgs) {
        throw new UnsupportedOperationException("The APK provider is read-only");
    }

    private void requireSupportedUri(Uri uri) {
        if (uri == null
                || !"content".equals(uri.getScheme())
                || !AUTHORITY.equals(uri.getAuthority())
                || !("/" + URI_PATH).equals(uri.getPath())) {
            throw new IllegalArgumentException("Unsupported APK URI");
        }
    }

    private File requirePreparedFile() throws FileNotFoundException {
        File file = getPreparedApkFile(getContext());
        try {
            File expected = file.getCanonicalFile();
            File cacheDirectory = new File(
                    getContext().getCacheDir(), CACHE_DIRECTORY).getCanonicalFile();
            if (!cacheDirectory.equals(expected.getParentFile())
                    || !expected.isFile()
                    || !expected.canRead()) {
                throw new FileNotFoundException("Prepared APK is unavailable");
            }
            return expected;
        } catch (java.io.IOException exception) {
            FileNotFoundException wrapped = new FileNotFoundException(
                    "Prepared APK is unavailable");
            wrapped.initCause(exception);
            throw wrapped;
        }
    }
}
