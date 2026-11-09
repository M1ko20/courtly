import { AlertCircle, ArrowUpLeft } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"

import { AuthLayout } from "@/components/shared/auth-layout"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordInput } from "@/components/shared/password-input"
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { useTranslation, type TranslationKey } from "@/lib/i18n"

/** Mirrors the accounts `backend/src/reservations/seed.py` creates. Shown in
 * dev builds, and in production only when VITE_SHOW_DEMO_ACCOUNTS=true (a
 * public demo deployment) — otherwise a production bundle must not advertise
 * working credentials. */
const DEMO_ACCOUNTS: { email: string; password: string; role: TranslationKey; hint: TranslationKey }[] =
  import.meta.env.DEV || import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === "true"
  ? [
      { email: "player@courtly.app", password: "playerplayer", role: "role.PLAYER", hint: "auth.demo.hint.player" },
      { email: "teammate@courtly.app", password: "teammate1", role: "role.PLAYER", hint: "auth.demo.hint.teammate" },
      { email: "manager@courtly.app", password: "managermanager", role: "role.VENUE_MANAGER", hint: "auth.demo.hint.manager" },
      { email: "admin@courtly.app", password: "adminadmin", role: "role.ADMIN", hint: "auth.demo.hint.admin" },
    ]
  : []

function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  function fillDemoAccount(demoEmail: string, demoPassword: string) {
    setEmail(demoEmail)
    setPassword(demoPassword)
    setError(null)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(email.trim(), password)
      const from = (location.state as { from?: { pathname: string; search?: string } } | null)?.from
      navigate(from ? `${from.pathname}${from.search ?? ""}` : "/app", { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("auth.error.login"))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title={t("auth.login.title")}
      description={t("auth.login.description")}
      footer={
        <>
          {t("auth.login.noAccount")}{" "}
          <Link to="/register" className="font-medium text-foreground underline underline-offset-4">
            {t("auth.login.signup")}
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate={false}>
        {error && (
          <div role="alert" className="flex animate-fade-in items-start gap-2 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger">
            <AlertCircle className="mt-px size-4 shrink-0" /> {error}
          </div>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">{t("auth.field.email")}</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            autoFocus
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={t("auth.field.emailPlaceholder")}
            className="h-10"
            aria-invalid={Boolean(error)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">{t("auth.field.password")}</Label>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="••••••••"
            className="h-10"
            aria-invalid={Boolean(error)}
          />
        </div>
        <Button type="submit" size="lg" className="mt-2 w-full" isLoading={isSubmitting}>
          {isSubmitting ? t("auth.login.submitting") : t("auth.login.submit")}
        </Button>
      </form>

      {DEMO_ACCOUNTS.length > 0 && (
        <section aria-labelledby="demo-accounts-title" className="mt-8 border-t-2 border-foreground pt-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="demo-accounts-title" className="font-mono text-[11px] tracking-[0.08em] uppercase">
              {t("auth.demo.title")}
            </h2>
            <span className="text-[12px] text-subtle-foreground">{t("auth.demo.description")}</span>
          </div>
          <ul className="mt-2 flex flex-col">
            {DEMO_ACCOUNTS.map((account) => {
              const selected = email === account.email && password === account.password
              return (
                <li key={account.email}>
                  <button
                    type="button"
                    onClick={() => fillDemoAccount(account.email, account.password)}
                    aria-pressed={selected}
                    className="group flex w-full items-center gap-3 border-b border-border py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:bg-muted aria-pressed:bg-muted"
                  >
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="flex items-baseline gap-2">
                        <span className="text-[14px] font-semibold">{t(account.role)}</span>
                        <span className="truncate text-[12px] text-muted-foreground">{t(account.hint)}</span>
                      </span>
                      <span className="truncate font-mono text-[11.5px] text-subtle-foreground">{account.email}</span>
                    </span>
                    <ArrowUpLeft
                      aria-hidden
                      className="size-4 shrink-0 text-subtle-foreground transition-colors group-hover:text-brand group-aria-pressed:text-brand"
                    />
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      )}
    </AuthLayout>
  )
}

export { LoginPage }
