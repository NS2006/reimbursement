import { t } from "../app/i18n";
import { BlueAlert } from "../components/blue/Alert";
import { BlueButton } from "../components/blue/Button";
import { BlueCard } from "../components/blue/Card";
import { BlueSelect } from "../components/blue/Select";
import { BlueSpinner } from "../components/blue/Spinner";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { useLoginController, type LoginController } from "../controllers/LoginController";
import type { User } from "../types/user";
import "../styles/pages/LoginPage.css";

interface LoginPageProps {
  onSignIn: (user: User) => void;
}

export default function LoginPage({ onSignIn }: LoginPageProps) {
  const controller = useLoginController(onSignIn);

  return (
    <main className="login-page">
      <LanguageSwitch className="login-page__language" />
      <div className="login-page__panel">
        <p className="login-page__brand">{t("app.name")}</p>
        <BlueCard title={t("login:title")}>
          <p className="login-page__intro">{t("login:intro")}</p>
          <UserPicker controller={controller} />
        </BlueCard>
        <p className="login-page__note">{t("login:note")}</p>
      </div>
    </main>
  );
}

function UserPicker({ controller }: { controller: LoginController }) {
  const { users, reloadUsers, email, selectEmail, submitting, loginError, submit } = controller;

  if (users.status === "loading") {
    return (
      <div className="login-page__picker login-page__picker--centered">
        <BlueSpinner label={t("login:loadingUsers")} />
      </div>
    );
  }

  if (users.status === "error") {
    return (
      <div className="login-page__picker">
        <BlueAlert variant="error" title={t("login:loadError")}>
          {users.message}
        </BlueAlert>
        <BlueButton variant="secondary" fullWidth onClick={reloadUsers}>
          {t("actions.tryAgain")}
        </BlueButton>
      </div>
    );
  }

  if (users.users.length === 0) {
    return (
      <BlueAlert variant="info" title={t("login:noUsers.title")}>
        {t("login:noUsers.text")}
      </BlueAlert>
    );
  }

  return (
    <form className="login-page__picker" onSubmit={submit}>
      <BlueSelect
        label={t("login:user")}
        placeholder={t("login:pickUser")}
        value={email}
        onChange={(event) => selectEmail(event.target.value)}
        options={users.users.map((user) => ({ value: user.email, label: `${user.name} (${user.email})` }))}
        required
      />
      {loginError ? <BlueAlert variant="error">{loginError}</BlueAlert> : null}
      <BlueButton type="submit" fullWidth loading={submitting} disabled={!email}>
        {t("login:continue")}
      </BlueButton>
    </form>
  );
}
