import { t } from "../app/i18n";
import { linkTo } from "../app/router";
import { BlueCard } from "../components/blue/Card";
import { BlueEmptyState } from "../components/blue/EmptyState";
import { BlueLink } from "../components/blue/Link";

export default function NotFoundPage() {
  return (
    <BlueCard>
      <BlueEmptyState title={t("title.notFound")} action={<BlueLink {...linkTo("/")}>{t("login:notFound.home")}</BlueLink>}>
        {t("login:notFound.text")}
      </BlueEmptyState>
    </BlueCard>
  );
}
