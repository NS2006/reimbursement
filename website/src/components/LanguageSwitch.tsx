import { LANGUAGES, language, setLanguage, t } from "../app/i18n";
import "../styles/components/LanguageSwitch.css";

/** ID | EN: the language the website is shown in. The choice is remembered in this browser. */
export function LanguageSwitch({ className = "" }: { className?: string }) {
  const current = language();
  return (
    <div className={`language-switch ${className}`.trim()} role="group" aria-label={t("language.label")}>
      {LANGUAGES.map((option) => (
        <button
          key={option}
          type="button"
          lang={option}
          className="language-switch__option"
          aria-pressed={option === current}
          title={t(`language.${option}`)}
          onClick={() => setLanguage(option)}
        >
          {option.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
