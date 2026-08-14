package org.brailleemotion.appmanager;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ComponentName;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.format.Formatter;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.text.Collator;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final String FACTORY_LAUNCHER_PACKAGE = "com.selvashc.launcher";
    private static final String FACTORY_LAUNCHER_ACTIVITY =
            "com.selvashc.launcher.LauncherActivity";
    private static final String FACTORY_MENU_SHORTCUT_PACKAGE =
            "com.selvashc.shortcut.appmanager";
    private static final long FIRST_ITEM_FOCUS_DELAY_MS = 40L;
    private static final int REQUEST_DOWNLOAD_PERMISSION = 4101;
    private static final int REQUEST_ALL_FILES_ACCESS = 4102;
    private static final int REQUEST_UNKNOWN_APP_SOURCES = 4103;
    private static final int REQUEST_INSTALL_APK = 4104;

    private enum ScreenMode {
        MAIN_MENU,
        LAUNCH_LIST,
        UNINSTALL_LIST,
        INSTALL_LIST,
        HELP_TOPICS,
        HELP_ARTICLE
    }

    private PackageManager packageManager;
    private AccessibilityManager accessibilityManager;
    private final Handler accessibilityHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService apkExecutor = Executors.newSingleThreadExecutor();
    private ScreenMode screenMode = ScreenMode.MAIN_MENU;

    private LinearLayout rootView;
    private TextView titleView;
    private TextView statusView;
    private ScrollView scrollView;
    private LinearLayout actionContainer;
    private Button backButton;
    private final ArrayList<Button> actionButtons = new ArrayList<Button>();
    private final ArrayList<AppEntry> visibleApps = new ArrayList<AppEntry>();
    private final ArrayList<ApkEntry> visibleApks = new ArrayList<ApkEntry>();

    private boolean firstResume = true;
    private String pendingUninstallPackage;
    private String pendingUninstallLabel;
    private boolean waitingForUninstallResult;
    private boolean waitingForInstallResult;
    private boolean waitingForPermissionSettings;
    private String pendingInstallPackage;
    private String pendingInstallLabel;
    private long pendingInstallVersionCode = -1L;
    private long pendingInstallPreviousVersionCode = -1L;
    private String installResultMessage;
    private int installListGeneration;
    private int selectedControlIndex = 0;
    private Runnable pendingFirstFocus;
    private boolean initialFocusRequested;
    private boolean forceInitialAccessibilityFocus;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        packageManager = getPackageManager();
        accessibilityManager =
                (AccessibilityManager) getSystemService(ACCESSIBILITY_SERVICE);
        buildInterface();
        showMainMenu();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        showMainMenu();
    }

    @Override
    protected void onResume() {
        super.onResume();

        if (firstResume) {
            firstResume = false;
            return;
        }

        if (waitingForUninstallResult) {
            waitingForUninstallResult = false;
            reportUninstallResult();
        }

        if (screenMode == ScreenMode.LAUNCH_LIST) {
            showApplicationList(ScreenMode.LAUNCH_LIST);
        } else if (screenMode == ScreenMode.UNINSTALL_LIST) {
            showApplicationList(ScreenMode.UNINSTALL_LIST);
        } else if (screenMode == ScreenMode.INSTALL_LIST
                && !waitingForInstallResult
                && !waitingForPermissionSettings) {
            showInstallableApkList();
        }
    }

    @Override
    protected void onDestroy() {
        cancelPendingAccessibilityWork();
        apkExecutor.shutdownNow();
        super.onDestroy();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_ALL_FILES_ACCESS) {
            waitingForPermissionSettings = false;
            if (hasDownloadAccess()) {
                openInstallSection();
            } else {
                showMainMenu();
                showMessage(getString(R.string.install_permission_not_granted));
            }
            return;
        }
        if (requestCode == REQUEST_UNKNOWN_APP_SOURCES) {
            waitingForPermissionSettings = false;
            if (canRequestPackageInstalls()) {
                showInstallableApkList();
            } else {
                showMainMenu();
                showMessage(getString(R.string.install_permission_not_granted));
            }
            return;
        }
        if (requestCode == REQUEST_INSTALL_APK) {
            waitingForInstallResult = false;
            reportInstallResult(resultCode);
            if (screenMode == ScreenMode.INSTALL_LIST) {
                showInstallableApkList();
            }
        }
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode,
            String[] permissions,
            int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_DOWNLOAD_PERMISSION) {
            return;
        }
        boolean granted = grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        if (granted) {
            openInstallSection();
        } else {
            showMainMenu();
            showMessage(getString(R.string.install_permission_not_granted));
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && initialFocusRequested) {
            scheduleFirstControlFocus();
        }
    }

    @Override
    public void onBackPressed() {
        if (screenMode == ScreenMode.MAIN_MENU) {
            exitToFactoryLauncher();
        } else if (screenMode == ScreenMode.HELP_ARTICLE) {
            showHelpTopics();
        } else {
            showMainMenu();
        }
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        int keyCode = event.getKeyCode();
        boolean navigationKey = isHandledNavigationKey(keyCode);

        if (event.getAction() == KeyEvent.ACTION_UP && navigationKey) {
            return true;
        }
        if (event.getAction() != KeyEvent.ACTION_DOWN || !navigationKey) {
            return super.dispatchKeyEvent(event);
        }

        // A real key press takes precedence over delayed screen announcements and
        // initial focus. Otherwise a fast user can move to item 2 and be pulled
        // back to item 1 when the delayed focus task runs.
        cancelPendingAccessibilityWork();

        switch (keyCode) {
            case KeyEvent.KEYCODE_DPAD_UP:
            case KeyEvent.KEYCODE_DPAD_LEFT:
                moveKeyboardFocus(-1);
                return true;

            case KeyEvent.KEYCODE_DPAD_DOWN:
            case KeyEvent.KEYCODE_DPAD_RIGHT:
                moveKeyboardFocus(1);
                return true;

            case KeyEvent.KEYCODE_TAB:
                moveKeyboardFocus(event.isShiftPressed() ? -1 : 1);
                return true;

            case KeyEvent.KEYCODE_PAGE_UP:
                moveKeyboardFocus(-5);
                return true;

            case KeyEvent.KEYCODE_PAGE_DOWN:
                moveKeyboardFocus(5);
                return true;

            case KeyEvent.KEYCODE_MOVE_HOME:
                focusControlAt(0);
                return true;

            case KeyEvent.KEYCODE_MOVE_END:
                focusControlAt(getKeyboardControls().size() - 1);
                return true;

            case KeyEvent.KEYCODE_ENTER:
            case KeyEvent.KEYCODE_NUMPAD_ENTER:
            case KeyEvent.KEYCODE_DPAD_CENTER:
            case KeyEvent.KEYCODE_SPACE:
            case KeyEvent.KEYCODE_BUTTON_A:
                if (event.getRepeatCount() == 0) {
                    activateFocusedControl();
                }
                return true;

            case KeyEvent.KEYCODE_ESCAPE:
                if (event.getRepeatCount() == 0) {
                    onBackPressed();
                }
                return true;

            default:
                return super.dispatchKeyEvent(event);
        }
    }

    private boolean isHandledNavigationKey(int keyCode) {
        switch (keyCode) {
            case KeyEvent.KEYCODE_DPAD_UP:
            case KeyEvent.KEYCODE_DPAD_LEFT:
            case KeyEvent.KEYCODE_DPAD_DOWN:
            case KeyEvent.KEYCODE_DPAD_RIGHT:
            case KeyEvent.KEYCODE_TAB:
            case KeyEvent.KEYCODE_PAGE_UP:
            case KeyEvent.KEYCODE_PAGE_DOWN:
            case KeyEvent.KEYCODE_MOVE_HOME:
            case KeyEvent.KEYCODE_MOVE_END:
            case KeyEvent.KEYCODE_ENTER:
            case KeyEvent.KEYCODE_NUMPAD_ENTER:
            case KeyEvent.KEYCODE_DPAD_CENTER:
            case KeyEvent.KEYCODE_SPACE:
            case KeyEvent.KEYCODE_BUTTON_A:
            case KeyEvent.KEYCODE_ESCAPE:
                return true;
            default:
                return false;
        }
    }

    private void buildInterface() {
        rootView = new LinearLayout(this);
        rootView.setOrientation(LinearLayout.VERTICAL);
        rootView.setPadding(dp(20), dp(14), dp(20), dp(12));
        rootView.setBackgroundColor(Color.WHITE);
        rootView.setFocusable(false);

        titleView = new TextView(this);
        titleView.setTextSize(28.0f);
        titleView.setTextColor(Color.BLACK);
        titleView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        titleView.setGravity(Gravity.START);
        titleView.setFocusable(false);
        titleView.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            titleView.setAccessibilityHeading(true);
        }
        rootView.addView(titleView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        statusView = new TextView(this);
        statusView.setTextSize(18.0f);
        statusView.setTextColor(Color.rgb(45, 45, 45));
        statusView.setPadding(0, dp(6), 0, dp(8));
        statusView.setFocusable(false);
        statusView.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        rootView.addView(statusView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setSmoothScrollingEnabled(false);
        scrollView.setFocusable(false);
        // The factory screen reader uses the nearest accessible scrollable ancestor
        // when its logical "next" command reaches the last visible child.  Hiding
        // this node made only the first screenful of applications reachable.
        scrollView.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        scrollView.setDescendantFocusability(ViewGroup.FOCUS_AFTER_DESCENDANTS);

        actionContainer = new LinearLayout(this);
        actionContainer.setOrientation(LinearLayout.VERTICAL);
        actionContainer.setFocusable(false);
        actionContainer.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_AUTO);
        scrollView.addView(actionContainer, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        rootView.addView(scrollView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1.0f));

        backButton = createAccessibleButton();
        backButton.setText(R.string.back_to_main_menu);
        backButton.setContentDescription(getString(R.string.back_button_description));
        backButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                onBackPressed();
            }
        });
        TextView hintView = new TextView(this);
        hintView.setText(R.string.navigation_hint);
        hintView.setTextSize(16.0f);
        hintView.setTextColor(Color.rgb(55, 55, 55));
        hintView.setPadding(0, dp(6), 0, 0);
        hintView.setFocusable(false);
        hintView.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        rootView.addView(hintView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        setContentView(rootView);
    }

    private Button createAccessibleButton() {
        final Button button = new Button(this);
        button.setId(View.generateViewId());
        button.setAllCaps(false);
        button.setTextSize(21.0f);
        button.setTextColor(Color.BLACK);
        button.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        button.setPadding(dp(16), dp(8), dp(16), dp(8));
        button.setMinimumHeight(dp(62));
        button.setFocusable(true);
        button.setFocusableInTouchMode(true);
        button.setClickable(true);
        button.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        button.setOnFocusChangeListener(new View.OnFocusChangeListener() {
            @Override
            public void onFocusChange(View view, boolean hasFocus) {
                if (hasFocus) {
                    synchronizeSelectionWithControl(button);
                }
            }
        });
        button.setAccessibilityDelegate(new View.AccessibilityDelegate() {
            @Override
            public boolean performAccessibilityAction(
                    View host,
                    int action,
                    Bundle arguments) {
                boolean handled = super.performAccessibilityAction(
                        host,
                        action,
                        arguments);
                if (action == AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS) {
                    synchronizeSelectionWithControl(button);
                }
                return handled;
            }
        });
        return button;
    }

    private void showMainMenu() {
        installListGeneration++;
        screenMode = ScreenMode.MAIN_MENU;
        setTitle(R.string.main_menu_title);
        titleView.setText(R.string.main_menu_title);
        statusView.setText(R.string.main_menu_status);
        backButton.setVisibility(View.GONE);
        configureBackToMainMenu();
        clearActions();

        addMainMenuButton(R.string.menu_launch, 0, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                showApplicationList(ScreenMode.LAUNCH_LIST);
            }
        });
        addMainMenuButton(R.string.menu_uninstall, 1, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                showApplicationList(ScreenMode.UNINSTALL_LIST);
            }
        });
        addMainMenuButton(R.string.menu_install, 2, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                openInstallSection();
            }
        });
        addMainMenuButton(R.string.menu_help, 3, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                showHelpTopics();
            }
        });
        addMainMenuButton(R.string.menu_exit, 4, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                exitToFactoryLauncher();
            }
        });

        linkDirectionalFocus();
        prepareScreenForAccessibility(getString(R.string.main_menu_title));
    }

    private void addMainMenuButton(
            int labelResource,
            int position,
            View.OnClickListener clickListener) {
        String label = getString(labelResource);
        Button button = createAccessibleButton();
        button.setText(label);
        button.setContentDescription(getString(
                R.string.main_action_description,
                label,
                position + 1,
                5));
        button.setOnClickListener(clickListener);
        addActionButton(button);
    }

    private void showApplicationList(ScreenMode requestedMode) {
        installListGeneration++;
        configureBackToMainMenu();
        screenMode = requestedMode;
        boolean uninstallMode = requestedMode == ScreenMode.UNINSTALL_LIST;
        titleView.setText(uninstallMode ? R.string.uninstall_title : R.string.launch_title);
        backButton.setVisibility(View.VISIBLE);
        clearActions();

        visibleApps.clear();
        visibleApps.addAll(loadLaunchableApplications(uninstallMode));

        if (visibleApps.isEmpty()) {
            statusView.setText(uninstallMode
                    ? R.string.empty_uninstall_list
                    : R.string.empty_launch_list);
        } else {
            statusView.setText(getString(
                    uninstallMode ? R.string.uninstall_count : R.string.launch_count,
                    visibleApps.size()));
        }

        for (int index = 0; index < visibleApps.size(); index++) {
            final AppEntry entry = visibleApps.get(index);
            Button button = createAccessibleButton();
            button.setText(getString(
                    R.string.application_button_text,
                    entry.label,
                    entry.packageName));
            button.setContentDescription(getString(
                    uninstallMode
                            ? R.string.uninstall_action_description
                            : R.string.launch_action_description,
                    entry.label,
                    index + 1,
                    visibleApps.size(),
                    entry.packageName));
            button.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View view) {
                    if (screenMode == ScreenMode.LAUNCH_LIST) {
                        launchApplication(entry);
                    } else if (screenMode == ScreenMode.UNINSTALL_LIST) {
                        confirmUninstall(entry);
                    }
                }
            });
            addActionButton(button);
        }

        // Keep "Back" after every application in the same scrollable hierarchy.
        // Otherwise a screen reader reaches this button after the last currently
        // visible application and wraps to the beginning without scrolling.
        addBackButtonToScrollableList();

        linkDirectionalFocus();
        String windowTitle = getString(
                uninstallMode
                        ? R.string.uninstall_window_title
                        : R.string.launch_window_title,
                visibleApps.size());
        prepareScreenForAccessibility(windowTitle);
    }

    private void showHelpTopics() {
        installListGeneration++;
        screenMode = ScreenMode.HELP_TOPICS;
        titleView.setText(R.string.help_menu_title);
        statusView.setText(R.string.help_menu_status);
        backButton.setVisibility(View.VISIBLE);
        configureBackToMainMenu();
        clearActions();

        final HelpContent.Topic[] topics = HelpContent.getTopics();
        for (int index = 0; index < topics.length; index++) {
            final HelpContent.Topic topic = topics[index];
            String title = getString(topic.titleResource);
            Button button = createAccessibleButton();
            button.setText(title);
            button.setContentDescription(getString(
                    R.string.help_topic_description,
                    title,
                    index + 1,
                    topics.length));
            button.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View view) {
                    showHelpArticle(topic);
                }
            });
            addActionButton(button);
        }

        addBackButtonToScrollableList();
        linkDirectionalFocus();
        prepareScreenForAccessibility(getString(
                R.string.help_menu_window_title,
                topics.length));
    }

    private void showHelpArticle(HelpContent.Topic topic) {
        installListGeneration++;
        screenMode = ScreenMode.HELP_ARTICLE;
        String topicTitle = getString(topic.titleResource);
        titleView.setText(topicTitle);
        statusView.setText(getString(
                R.string.help_article_status,
                topic.paragraphResources.length));
        backButton.setVisibility(View.VISIBLE);
        configureBackToHelpTopics();
        clearActions();

        for (int index = 0; index < topic.paragraphResources.length; index++) {
            String paragraph = getString(topic.paragraphResources[index]);
            final String description = getString(
                    R.string.help_paragraph_description,
                    index + 1,
                    topic.paragraphResources.length,
                    paragraph);
            Button button = createAccessibleButton();
            button.setText(paragraph);
            button.setContentDescription(description);
            button.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View view) {
                    announceNow(description);
                }
            });
            addActionButton(button);
        }

        addBackButtonToScrollableList();
        linkDirectionalFocus();
        prepareScreenForAccessibility(getString(
                R.string.help_article_window_title,
                topicTitle,
                topic.paragraphResources.length), true);
    }

    private void openInstallSection() {
        if (!hasDownloadAccess()) {
            showPermissionDialog(
                    getString(R.string.download_permission_title),
                    getString(R.string.download_permission_message),
                    new Runnable() {
                        @Override
                        public void run() {
                            requestDownloadAccess();
                        }
                    });
            return;
        }
        if (!canRequestPackageInstalls()) {
            showPermissionDialog(
                    getString(R.string.install_source_permission_title),
                    getString(R.string.install_source_permission_message),
                    new Runnable() {
                        @Override
                        public void run() {
                            requestUnknownAppSourcesAccess();
                        }
                    });
            return;
        }
        showInstallableApkList();
    }

    private void showInstallableApkList() {
        final int generation = ++installListGeneration;
        screenMode = ScreenMode.INSTALL_LIST;
        configureBackToMainMenu();
        titleView.setText(R.string.install_title);
        statusView.setText(R.string.scanning_apk_files);
        backButton.setVisibility(View.VISIBLE);
        clearActions();
        visibleApks.clear();
        addBackButtonToScrollableList();
        linkDirectionalFocus();
        prepareScreenForAccessibility(getString(R.string.scanning_apk_window_title));

        apkExecutor.execute(new Runnable() {
            @Override
            public void run() {
                final ApkRepository.ScanResult result =
                        ApkRepository.scanDownloads(packageManager);
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (isFinishing()
                                || screenMode != ScreenMode.INSTALL_LIST
                                || generation != installListGeneration) {
                            return;
                        }
                        renderInstallableApkList(result);
                    }
                });
            }
        });
    }

    private void renderInstallableApkList(ApkRepository.ScanResult result) {
        clearActions();
        configureBackToMainMenu();
        visibleApks.clear();
        visibleApks.addAll(result.entries);

        String listStatus;
        if (result.directoryUnavailable) {
            listStatus = getString(R.string.download_directory_unavailable);
        } else if (visibleApks.isEmpty()) {
            listStatus = result.invalidApkCount > 0
                    ? getString(R.string.empty_install_list_with_invalid,
                            result.invalidApkCount)
                    : getString(R.string.empty_install_list);
        } else {
            listStatus = getString(
                    R.string.install_count,
                    visibleApks.size(),
                    result.invalidApkCount);
        }
        statusView.setText(installResultMessage == null
                ? listStatus
                : installResultMessage + " " + listStatus);

        for (int index = 0; index < visibleApks.size(); index++) {
            final ApkEntry entry = visibleApks.get(index);
            String size = Formatter.formatShortFileSize(this, entry.sizeBytes);
            Button button = createAccessibleButton();
            button.setText(getString(
                    R.string.apk_button_text,
                    entry.label,
                    entry.fileName));
            button.setContentDescription(getString(
                    R.string.install_action_description,
                    entry.label,
                    index + 1,
                    visibleApks.size(),
                    entry.fileName,
                    entry.packageName,
                    entry.versionName,
                    size));
            button.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View view) {
                    confirmInstall(entry);
                }
            });
            addActionButton(button);
        }

        if (visibleApks.isEmpty()) {
            backButton.setContentDescription(
                    listStatus + " " + getString(R.string.back_button_description));
        }
        addBackButtonToScrollableList();
        linkDirectionalFocus();
        String baseWindowTitle = getString(
                R.string.install_window_title,
                visibleApks.size());
        String windowTitle = installResultMessage == null
                ? baseWindowTitle
                : installResultMessage + " " + baseWindowTitle;
        installResultMessage = null;
        prepareScreenForAccessibility(windowTitle);
    }

    private void clearActions() {
        cancelPendingAccessibilityWork();
        selectedControlIndex = 0;
        backButton.setEnabled(true);
        actionButtons.clear();
        actionContainer.removeAllViews();
        scrollView.scrollTo(0, 0);
    }

    private void addActionButton(Button button) {
        LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        layout.bottomMargin = dp(6);
        actionContainer.addView(button, layout);
        actionButtons.add(button);
    }

    private void addBackButtonToScrollableList() {
        LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        layout.topMargin = dp(6);
        actionContainer.addView(backButton, layout);
    }

    private void configureBackToMainMenu() {
        backButton.setText(R.string.back_to_main_menu);
        backButton.setContentDescription(getString(R.string.back_button_description));
    }

    private void configureBackToHelpTopics() {
        backButton.setText(R.string.back_to_help_topics);
        backButton.setContentDescription(getString(
                R.string.back_to_help_topics_description));
    }

    private void linkDirectionalFocus() {
        ArrayList<Button> controls = getKeyboardControls();
        if (controls.isEmpty()) {
            return;
        }

        for (int index = 0; index < controls.size(); index++) {
            Button current = controls.get(index);
            Button previous = controls.get(index == 0 ? controls.size() - 1 : index - 1);
            Button next = controls.get(index == controls.size() - 1 ? 0 : index + 1);
            current.setNextFocusUpId(previous.getId());
            current.setNextFocusLeftId(previous.getId());
            current.setNextFocusDownId(next.getId());
            current.setNextFocusRightId(next.getId());
        }
    }

    private ArrayList<Button> getKeyboardControls() {
        ArrayList<Button> controls = new ArrayList<Button>(actionButtons);
        if (backButton.getVisibility() == View.VISIBLE
                && backButton.getParent() == actionContainer) {
            controls.add(backButton);
        }
        return controls;
    }

    private void moveKeyboardFocus(int delta) {
        ArrayList<Button> controls = getKeyboardControls();
        if (controls.isEmpty()) {
            announceNow(getString(R.string.no_controls_announcement));
            return;
        }

        int focusedIndex = findFocusedControlIndex(controls);
        int currentIndex = focusedIndex >= 0 ? focusedIndex : selectedControlIndex;
        int size = controls.size();
        currentIndex = ((currentIndex + delta) % size + size) % size;
        focusControlAtIndex(controls, currentIndex);
    }

    private void focusControlAt(int requestedIndex) {
        ArrayList<Button> controls = getKeyboardControls();
        if (controls.isEmpty()) {
            announceNow(getString(R.string.no_controls_announcement));
            return;
        }
        int safeIndex = Math.max(0, Math.min(requestedIndex, controls.size() - 1));
        focusControlAtIndex(controls, safeIndex);
    }

    private int findFocusedControlIndex(List<Button> controls) {
        View focused = getCurrentFocus();
        for (int index = 0; index < controls.size(); index++) {
            if (controls.get(index) == focused) {
                return index;
            }
        }
        return -1;
    }

    private void focusControlAtIndex(List<Button> controls, int index) {
        if (controls.isEmpty()) {
            return;
        }
        int safeIndex = Math.max(0, Math.min(index, controls.size() - 1));
        applySelectedControl(controls, safeIndex);

        Button button = controls.get(safeIndex);
        button.requestFocus();
        if (button.getParent() == actionContainer) {
            scrollView.requestChildFocus(button, button);
        }
    }

    private void synchronizeSelectionWithControl(Button selectedButton) {
        if (pendingFirstFocus != null) {
            accessibilityHandler.removeCallbacks(pendingFirstFocus);
            pendingFirstFocus = null;
        }
        ArrayList<Button> controls = getKeyboardControls();
        int selectedIndex = controls.indexOf(selectedButton);
        if (selectedIndex >= 0) {
            applySelectedControl(controls, selectedIndex);
        }
    }

    private void applySelectedControl(List<Button> controls, int selectedIndex) {
        selectedControlIndex = selectedIndex;
        for (int controlIndex = 0; controlIndex < controls.size(); controlIndex++) {
            boolean selected = controlIndex == selectedIndex;
            Button control = controls.get(controlIndex);
            control.setBackgroundColor(selected
                    ? Color.rgb(196, 219, 255)
                    : Color.rgb(238, 238, 238));
        }
    }

    private void activateFocusedControl() {
        ArrayList<Button> controls = getKeyboardControls();
        if (!controls.isEmpty()) {
            int safeIndex = Math.max(0, Math.min(
                    selectedControlIndex,
                    controls.size() - 1));
            controls.get(safeIndex).performClick();
        }
    }

    private void prepareScreenForAccessibility(String windowTitle) {
        prepareScreenForAccessibility(windowTitle, false);
    }

    private void prepareScreenForAccessibility(
            String windowTitle,
            boolean forceAccessibilityFocus) {
        cancelPendingAccessibilityWork();
        forceInitialAccessibilityFocus = forceAccessibilityFocus;
        setTitle(windowTitle);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            rootView.setAccessibilityPaneTitle(windowTitle);
        }
        initialFocusRequested = true;
        if (hasWindowFocus()) {
            scheduleFirstControlFocus();
        }
    }

    private void scheduleFirstControlFocus() {
        if (pendingFirstFocus != null) {
            accessibilityHandler.removeCallbacks(pendingFirstFocus);
        }
        pendingFirstFocus = new Runnable() {
            @Override
            public void run() {
                pendingFirstFocus = null;
                initialFocusRequested = false;
                boolean forceAccessibilityFocus = forceInitialAccessibilityFocus;
                forceInitialAccessibilityFocus = false;
                if (!actionButtons.isEmpty()) {
                    focusControlAtIndex(getKeyboardControls(), 0);
                    if (forceAccessibilityFocus) {
                        actionButtons.get(0).performAccessibilityAction(
                                AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS,
                                null);
                    }
                } else if (backButton.getVisibility() == View.VISIBLE) {
                    focusControlAtIndex(getKeyboardControls(), 0);
                }
            }
        };
        accessibilityHandler.postDelayed(
                pendingFirstFocus,
                FIRST_ITEM_FOCUS_DELAY_MS);
    }

    private void announceNow(CharSequence text) {
        if (text == null || text.length() == 0) {
            return;
        }
        if (accessibilityManager != null
                && accessibilityManager.isEnabled()
                && rootView != null
                && rootView.isAttachedToWindow()) {
            rootView.announceForAccessibility(text);
        }
    }

    private void cancelPendingAccessibilityWork() {
        initialFocusRequested = false;
        forceInitialAccessibilityFocus = false;
        if (pendingFirstFocus != null) {
            accessibilityHandler.removeCallbacks(pendingFirstFocus);
            pendingFirstFocus = null;
        }
    }

    private List<AppEntry> loadLaunchableApplications(boolean uninstallMode) {
        Intent launcherQuery = new Intent(Intent.ACTION_MAIN);
        launcherQuery.addCategory(Intent.CATEGORY_LAUNCHER);

        List<ResolveInfo> activities;
        try {
            activities = packageManager.queryIntentActivities(launcherQuery, 0);
        } catch (SecurityException exception) {
            activities = Collections.emptyList();
        }

        Map<String, AppEntry> packages = new LinkedHashMap<String, AppEntry>();
        for (ResolveInfo resolveInfo : activities) {
            if (resolveInfo.activityInfo == null
                    || resolveInfo.activityInfo.applicationInfo == null) {
                continue;
            }

            ApplicationInfo applicationInfo = resolveInfo.activityInfo.applicationInfo;
            String packageName = applicationInfo.packageName;
            if (packageName == null
                    || packageName.equals(getPackageName())
                    || packageName.equals(FACTORY_MENU_SHORTCUT_PACKAGE)) {
                continue;
            }
            if (!applicationInfo.enabled || !resolveInfo.activityInfo.enabled) {
                continue;
            }
            if (uninstallMode && !isSafeToOfferForUninstall(applicationInfo)) {
                continue;
            }
            if (packages.containsKey(packageName)) {
                continue;
            }

            CharSequence loadedLabel = resolveInfo.loadLabel(packageManager);
            String label = loadedLabel == null
                    ? packageName
                    : loadedLabel.toString().trim();
            if (label.length() == 0) {
                label = packageName;
            }

            Intent launchIntent = new Intent(Intent.ACTION_MAIN);
            launchIntent.addCategory(Intent.CATEGORY_LAUNCHER);
            launchIntent.setComponent(new ComponentName(
                    resolveInfo.activityInfo.packageName,
                    resolveInfo.activityInfo.name));
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                    | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
            packages.put(packageName, new AppEntry(label, packageName, launchIntent));
        }

        ArrayList<AppEntry> result = new ArrayList<AppEntry>(packages.values());
        final Collator collator = Collator.getInstance(new Locale("ru", "RU"));
        collator.setStrength(Collator.PRIMARY);
        Collections.sort(result, new Comparator<AppEntry>() {
            @Override
            public int compare(AppEntry left, AppEntry right) {
                int labelResult = collator.compare(left.label, right.label);
                if (labelResult != 0) {
                    return labelResult;
                }
                return left.packageName.compareToIgnoreCase(right.packageName);
            }
        });
        return result;
    }

    private boolean isSafeToOfferForUninstall(ApplicationInfo applicationInfo) {
        int flags = applicationInfo.flags;
        boolean systemApplication = (flags & ApplicationInfo.FLAG_SYSTEM) != 0;
        boolean updatedSystemApplication =
                (flags & ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) != 0;
        String packageName = applicationInfo.packageName;

        if (systemApplication || updatedSystemApplication) {
            return false;
        }
        if (packageName == null || packageName.equals(getPackageName())) {
            return false;
        }
        if (packageName.equals(FACTORY_LAUNCHER_PACKAGE)) {
            return false;
        }
        return !packageName.startsWith("com.selvashc.")
                && !packageName.startsWith("com.hims.");
    }

    private void launchApplication(AppEntry entry) {
        cancelPendingAccessibilityWork();
        try {
            startActivity(entry.launchIntent);
        } catch (ActivityNotFoundException | SecurityException exception) {
            String message = getString(R.string.launch_failed, entry.label);
            Toast.makeText(this, message, Toast.LENGTH_LONG).show();
            announceNow(message);
            showApplicationList(ScreenMode.LAUNCH_LIST);
        }
    }

    private void confirmUninstall(final AppEntry entry) {
        final String warning = getString(
                R.string.uninstall_warning,
                entry.label,
                entry.packageName);
        showAccessibleTwoActionDialog(
                getString(R.string.uninstall_question),
                warning,
                getString(R.string.cancel_uninstall_description, warning),
                getString(R.string.continue_uninstall_description),
                new Runnable() {
                    @Override
                    public void run() {
                        requestSystemUninstall(entry);
                    }
                });
    }

    private void confirmInstall(final ApkEntry entry) {
        String size = Formatter.formatShortFileSize(this, entry.sizeBytes);
        final String details = getString(
                R.string.install_warning,
                entry.label,
                entry.fileName,
                entry.packageName,
                entry.versionName,
                size);
        showAccessibleTwoActionDialog(
                getString(R.string.install_question),
                details,
                getString(R.string.cancel_install_description, details),
                getString(R.string.continue_install_description),
                new Runnable() {
                    @Override
                    public void run() {
                        prepareAndRequestSystemInstall(entry);
                    }
                });
    }

    private void showPermissionDialog(
            String title,
            String message,
            final Runnable continueAction) {
        showAccessibleTwoActionDialog(
                title,
                message,
                getString(R.string.cancel_permission_description, message),
                getString(R.string.continue_permission_description),
                continueAction);
    }

    private void showAccessibleTwoActionDialog(
            final String title,
            final String message,
            final String cancelDescription,
            final String continueDescription,
            final Runnable continueAction) {
        final AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle(title)
                .setMessage(message)
                .setNegativeButton(R.string.cancel_action, null)
                .setPositiveButton(R.string.continue_action, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface shownDialog, int which) {
                        continueAction.run();
                    }
                })
                .create();
        dialog.setOnShowListener(new DialogInterface.OnShowListener() {
            @Override
            public void onShow(DialogInterface shownDialog) {
                Button cancelButton = dialog.getButton(AlertDialog.BUTTON_NEGATIVE);
                Button continueButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE);
                TextView messageView = dialog.findViewById(android.R.id.message);

                // The warning remains visible, but it is included in the safe
                // Cancel action's description. This prevents the factory screen
                // reader from leaving keyboard focus on non-actionable text.
                if (messageView != null) {
                    messageView.setImportantForAccessibility(
                            View.IMPORTANT_FOR_ACCESSIBILITY_NO);
                }
                if (cancelButton != null) {
                    cancelButton.setContentDescription(cancelDescription);
                    if (continueButton != null && Build.VERSION.SDK_INT >= 22) {
                        cancelButton.setAccessibilityTraversalBefore(
                                continueButton.getId());
                    }
                    cancelButton.requestFocus();
                }
                if (continueButton != null) {
                    continueButton.setContentDescription(continueDescription);
                }
                if (dialog.getWindow() != null
                        && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    dialog.getWindow().getDecorView().setAccessibilityPaneTitle(
                            title);
                }
            }
        });
        dialog.setOnKeyListener(new DialogInterface.OnKeyListener() {
            @Override
            public boolean onKey(DialogInterface shownDialog, int keyCode, KeyEvent event) {
                boolean handled = isHandledNavigationKey(keyCode);
                if (event.getAction() == KeyEvent.ACTION_UP && handled) {
                    return true;
                }
                if (event.getAction() != KeyEvent.ACTION_DOWN || !handled) {
                    return false;
                }

                Button cancelButton = dialog.getButton(AlertDialog.BUTTON_NEGATIVE);
                Button continueButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE);
                switch (keyCode) {
                    case KeyEvent.KEYCODE_DPAD_UP:
                    case KeyEvent.KEYCODE_DPAD_LEFT:
                    case KeyEvent.KEYCODE_PAGE_UP:
                    case KeyEvent.KEYCODE_MOVE_HOME:
                        return requestDialogButtonFocus(cancelButton);

                    case KeyEvent.KEYCODE_DPAD_DOWN:
                    case KeyEvent.KEYCODE_DPAD_RIGHT:
                    case KeyEvent.KEYCODE_PAGE_DOWN:
                    case KeyEvent.KEYCODE_MOVE_END:
                        return requestDialogButtonFocus(continueButton);

                    case KeyEvent.KEYCODE_TAB:
                        return requestDialogButtonFocus(event.isShiftPressed()
                                ? cancelButton
                                : continueButton);

                    case KeyEvent.KEYCODE_ENTER:
                    case KeyEvent.KEYCODE_NUMPAD_ENTER:
                    case KeyEvent.KEYCODE_DPAD_CENTER:
                    case KeyEvent.KEYCODE_SPACE:
                    case KeyEvent.KEYCODE_BUTTON_A:
                        if (event.getRepeatCount() == 0) {
                            View focused = dialog.getCurrentFocus();
                            Button action = focused == continueButton
                                    ? continueButton
                                    : cancelButton;
                            if (action != null) {
                                action.performClick();
                            }
                        }
                        return true;

                    case KeyEvent.KEYCODE_ESCAPE:
                        if (event.getRepeatCount() == 0) {
                            dialog.cancel();
                        }
                        return true;

                    default:
                        return false;
                }
            }
        });
        dialog.show();
    }

    private boolean requestDialogButtonFocus(Button button) {
        if (button != null) {
            button.requestFocus();
        }
        return true;
    }

    private boolean hasDownloadAccess() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            return Environment.isExternalStorageManager();
        }
        return checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED;
    }

    private boolean canRequestPackageInstalls() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O
                || packageManager.canRequestPackageInstalls();
    }

    private void requestDownloadAccess() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            requestPermissions(
                    new String[]{Manifest.permission.READ_EXTERNAL_STORAGE},
                    REQUEST_DOWNLOAD_PERMISSION);
            return;
        }

        Intent settingsIntent = new Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:" + getPackageName()));
        waitingForPermissionSettings = true;
        try {
            startActivityForResult(settingsIntent, REQUEST_ALL_FILES_ACCESS);
        } catch (ActivityNotFoundException | SecurityException exception) {
            settingsIntent = new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION);
            try {
                startActivityForResult(settingsIntent, REQUEST_ALL_FILES_ACCESS);
            } catch (ActivityNotFoundException | SecurityException fallbackException) {
                waitingForPermissionSettings = false;
                showMessage(getString(R.string.permission_settings_failed));
            }
        }
    }

    private void requestUnknownAppSourcesAccess() {
        Intent settingsIntent = new Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + getPackageName()));
        waitingForPermissionSettings = true;
        try {
            startActivityForResult(settingsIntent, REQUEST_UNKNOWN_APP_SOURCES);
        } catch (ActivityNotFoundException | SecurityException exception) {
            waitingForPermissionSettings = false;
            showMessage(getString(R.string.permission_settings_failed));
        }
    }

    private void prepareAndRequestSystemInstall(final ApkEntry entry) {
        final int generation = installListGeneration;
        statusView.setText(R.string.preparing_apk);
        setKeyboardControlsEnabled(false);
        announceNow(getString(R.string.preparing_apk));

        apkExecutor.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    ApkInstaller.prepare(MainActivity.this, entry);
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (isFinishing()
                                    || screenMode != ScreenMode.INSTALL_LIST
                                    || generation != installListGeneration) {
                                ApkInstaller.clearPrepared(MainActivity.this);
                                return;
                            }
                            requestSystemInstall(entry);
                        }
                    });
                } catch (final Exception exception) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (isFinishing()
                                    || screenMode != ScreenMode.INSTALL_LIST
                                    || generation != installListGeneration) {
                                ApkInstaller.clearPrepared(MainActivity.this);
                                return;
                            }
                            ApkInstaller.clearPrepared(MainActivity.this);
                            setKeyboardControlsEnabled(true);
                            showMessage(getString(
                                    R.string.apk_prepare_failed,
                                    entry.label));
                            showInstallableApkList();
                        }
                    });
                }
            }
        });
    }

    private void setKeyboardControlsEnabled(boolean enabled) {
        for (Button control : getKeyboardControls()) {
            control.setEnabled(enabled);
        }
    }

    private void requestSystemInstall(ApkEntry entry) {
        Uri apkUri = ApkInstallFileProvider.getPreparedApkUri();
        Intent installIntent = new Intent(Intent.ACTION_INSTALL_PACKAGE);
        installIntent.setData(apkUri);
        installIntent.setClipData(ClipData.newUri(
                getContentResolver(),
                entry.fileName,
                apkUri));
        installIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        installIntent.putExtra(Intent.EXTRA_RETURN_RESULT, true);

        pendingInstallPackage = entry.packageName;
        pendingInstallLabel = entry.label;
        pendingInstallVersionCode = entry.versionCode;
        pendingInstallPreviousVersionCode = getInstalledVersionCode(entry.packageName);
        try {
            waitingForInstallResult = true;
            showMessage(getString(R.string.install_requested));
            startActivityForResult(installIntent, REQUEST_INSTALL_APK);
        } catch (ActivityNotFoundException | SecurityException exception) {
            waitingForInstallResult = false;
            clearPendingInstall();
            setKeyboardControlsEnabled(true);
            showMessage(getString(R.string.install_failed, entry.label));
        }
    }

    private void reportInstallResult(int resultCode) {
        if (pendingInstallPackage == null || pendingInstallLabel == null) {
            return;
        }
        long installedVersion = getInstalledVersionCode(pendingInstallPackage);
        boolean installed = resultCode == Activity.RESULT_OK
                || (installedVersion == pendingInstallVersionCode
                        && installedVersion != pendingInstallPreviousVersionCode);
        String message = getString(
                installed ? R.string.install_complete : R.string.install_not_complete,
                pendingInstallLabel);
        installResultMessage = message;
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
        clearPendingInstall();
    }

    private long getInstalledVersionCode(String packageName) {
        try {
            PackageInfo packageInfo = packageManager.getPackageInfo(packageName, 0);
            return Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                    ? packageInfo.getLongVersionCode()
                    : packageInfo.versionCode;
        } catch (PackageManager.NameNotFoundException exception) {
            return -1L;
        }
    }

    private void clearPendingInstall() {
        ApkInstaller.clearPrepared(this);
        pendingInstallPackage = null;
        pendingInstallLabel = null;
        pendingInstallVersionCode = -1L;
        pendingInstallPreviousVersionCode = -1L;
    }

    private void showMessage(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
        announceNow(message);
    }

    private void requestSystemUninstall(AppEntry entry) {
        Intent uninstallIntent = new Intent(
                Intent.ACTION_DELETE,
                Uri.parse("package:" + entry.packageName));
        pendingUninstallPackage = entry.packageName;
        pendingUninstallLabel = entry.label;

        try {
            waitingForUninstallResult = true;
            String message = getString(R.string.uninstall_requested);
            Toast.makeText(this, message, Toast.LENGTH_LONG).show();
            announceNow(message);
            startActivity(uninstallIntent);
        } catch (ActivityNotFoundException | SecurityException exception) {
            waitingForUninstallResult = false;
            pendingUninstallPackage = null;
            pendingUninstallLabel = null;
            String message = getString(R.string.uninstall_failed, entry.label);
            Toast.makeText(this, message, Toast.LENGTH_LONG).show();
            announceNow(message);
        }
    }

    private void reportUninstallResult() {
        if (pendingUninstallPackage == null || pendingUninstallLabel == null) {
            return;
        }

        boolean stillInstalled = isPackageInstalled(pendingUninstallPackage);
        int messageResource = stillInstalled
                ? R.string.uninstall_not_complete
                : R.string.uninstall_complete;
        String message = getString(messageResource, pendingUninstallLabel);
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
        announceNow(message);

        pendingUninstallPackage = null;
        pendingUninstallLabel = null;
    }

    private boolean isPackageInstalled(String packageName) {
        try {
            packageManager.getPackageInfo(packageName, 0);
            return true;
        } catch (PackageManager.NameNotFoundException exception) {
            return false;
        }
    }

    private void exitToFactoryLauncher() {
        cancelPendingAccessibilityWork();
        Intent factoryHome = new Intent(Intent.ACTION_MAIN);
        factoryHome.addCategory(Intent.CATEGORY_HOME);
        factoryHome.setComponent(new ComponentName(
                FACTORY_LAUNCHER_PACKAGE,
                FACTORY_LAUNCHER_ACTIVITY));
        factoryHome.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_CLEAR_TOP
                | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);

        try {
            startActivity(factoryHome);
            finishAffinity();
            return;
        } catch (ActivityNotFoundException | SecurityException exception) {
            // Fall back to the current HOME if the known factory component changed.
        }

        Intent genericHome = new Intent(Intent.ACTION_MAIN);
        genericHome.addCategory(Intent.CATEGORY_HOME);
        genericHome.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        try {
            startActivity(genericHome);
            finishAffinity();
        } catch (ActivityNotFoundException | SecurityException exception) {
            String message = getString(R.string.factory_launcher_failed);
            Toast.makeText(this, message, Toast.LENGTH_LONG).show();
            announceNow(message);
        }
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
    }

    private static final class AppEntry {
        final String label;
        final String packageName;
        final Intent launchIntent;

        AppEntry(String label, String packageName, Intent launchIntent) {
            this.label = label;
            this.packageName = packageName;
            this.launchIntent = launchIntent;
        }
    }
}
