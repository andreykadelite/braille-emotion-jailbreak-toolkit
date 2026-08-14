package org.brailleemotion.appmanager;

final class HelpContent {
    private HelpContent() {
    }

    static Topic[] getTopics() {
        return new Topic[]{
                new Topic(
                        R.string.help_topic_responsibility,
                        new int[]{
                                R.string.help_responsibility_p1,
                                R.string.help_responsibility_p2,
                                R.string.help_responsibility_p3,
                                R.string.help_responsibility_p4,
                                R.string.help_responsibility_p5,
                                R.string.help_responsibility_p6
                        }),
                new Topic(
                        R.string.help_topic_before_start,
                        new int[]{
                                R.string.help_before_start_p1,
                                R.string.help_before_start_p2,
                                R.string.help_before_start_p3,
                                R.string.help_before_start_p4,
                                R.string.help_before_start_p5
                        }),
                new Topic(
                        R.string.help_topic_main_menu,
                        new int[]{
                                R.string.help_main_menu_p1,
                                R.string.help_main_menu_p2,
                                R.string.help_main_menu_p3,
                                R.string.help_main_menu_p4,
                                R.string.help_main_menu_p5
                        }),
                new Topic(
                        R.string.help_topic_navigation,
                        new int[]{
                                R.string.help_navigation_p1,
                                R.string.help_navigation_p2,
                                R.string.help_navigation_p3,
                                R.string.help_navigation_p4,
                                R.string.help_navigation_p5
                        }),
                new Topic(
                        R.string.help_topic_installation,
                        new int[]{
                                R.string.help_installation_p1,
                                R.string.help_installation_p2,
                                R.string.help_installation_p3,
                                R.string.help_installation_p4,
                                R.string.help_installation_p5,
                                R.string.help_installation_p6,
                                R.string.help_installation_p7
                        }),
                new Topic(
                        R.string.help_topic_launching,
                        new int[]{
                                R.string.help_launching_p1,
                                R.string.help_launching_p2,
                                R.string.help_launching_p3,
                                R.string.help_launching_p4
                        }),
                new Topic(
                        R.string.help_topic_uninstalling,
                        new int[]{
                                R.string.help_uninstalling_p1,
                                R.string.help_uninstalling_p2,
                                R.string.help_uninstalling_p3,
                                R.string.help_uninstalling_p4,
                                R.string.help_uninstalling_p5
                        }),
                new Topic(
                        R.string.help_topic_permissions,
                        new int[]{
                                R.string.help_permissions_p1,
                                R.string.help_permissions_p2,
                                R.string.help_permissions_p3,
                                R.string.help_permissions_p4,
                                R.string.help_permissions_p5,
                                R.string.help_permissions_p6
                        }),
                new Topic(
                        R.string.help_topic_security,
                        new int[]{
                                R.string.help_security_p1,
                                R.string.help_security_p2,
                                R.string.help_security_p3,
                                R.string.help_security_p4,
                                R.string.help_security_p5,
                                R.string.help_security_p6
                        }),
                new Topic(
                        R.string.help_topic_troubleshooting,
                        new int[]{
                                R.string.help_troubleshooting_p1,
                                R.string.help_troubleshooting_p2,
                                R.string.help_troubleshooting_p3,
                                R.string.help_troubleshooting_p4,
                                R.string.help_troubleshooting_p5,
                                R.string.help_troubleshooting_p6,
                                R.string.help_troubleshooting_p7
                        }),
                new Topic(
                        R.string.help_topic_about,
                        new int[]{
                                R.string.help_about_p1,
                                R.string.help_about_p2,
                                R.string.help_about_p3,
                                R.string.help_about_p4
                        })
        };
    }

    static final class Topic {
        final int titleResource;
        final int[] paragraphResources;

        Topic(int titleResource, int[] paragraphResources) {
            this.titleResource = titleResource;
            this.paragraphResources = paragraphResources;
        }
    }
}
