import type { ReactNode } from "react";
import { t } from "../app/i18n";
import { followLink, linkTo } from "../app/router";
import { BlueAvatar } from "../components/blue/Avatar";
import { BlueButton } from "../components/blue/Button";
import { BlueNavbar } from "../components/blue/Navbar";
import type { BlueNavItem } from "../components/blue/types";
import { LanguageSwitch } from "../components/LanguageSwitch";
import type { User } from "../types/user";
import "../styles/layouts/AppLayout.css";

interface AppLayoutProps {
  user: User;
  onSwitchUser: () => void;
  /** The main links of the navbar. */
  navItems: BlueNavItem[];
  /** key of the navbar link of the open page. */
  activeNavKey?: string;
  /** A wider content area, for pages that show a photo next to tables (the BBM report). */
  wide?: boolean;
  children: ReactNode;
}

// Frame for every signed-in page: the navbar (links, language, current user) on top, the page content below.
export default function AppLayout({ user, onSwitchUser, navItems, activeNavKey, wide = false, children }: AppLayoutProps) {
  return (
    <div className="app-layout">
      <BlueNavbar
        className="app-layout__navbar"
        logo={
          <a className="app-layout__brand" {...linkTo("/")}>
            {t("app.name")}
          </a>
        }
        items={navItems}
        activeKey={activeNavKey}
        onNavigate={(_item, event) => followLink(event)}
        actions={
          <>
            <LanguageSwitch />
            <div className="app-layout__user">
              <BlueAvatar name={user.name} />
              <span className="app-layout__user-text">
                <span className="app-layout__user-name">{user.name}</span>
                <span className="app-layout__user-email">{user.email}</span>
              </span>
              <BlueButton variant="secondary" size="sm" onClick={onSwitchUser}>
                {t("user.switch")}
              </BlueButton>
            </div>
          </>
        }
      />
      <main className={`app-layout__content ${wide ? "app-layout__content--wide" : ""}`.trim()}>{children}</main>
    </div>
  );
}
