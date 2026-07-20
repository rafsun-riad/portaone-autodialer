"use client";

import { Button } from "@heroui/react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { LockKeyhole, ShieldCheck, UserRound } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError, apiRequest } from "@/lib/client-api";

const loginSchema = z.object({
  username: z.string().min(1, "Username is required."),
  password: z.string().min(1, "Password is required."),
});

const changePasswordSchema = z
  .object({
    newPassword: z
      .string()
      .min(8, "New password must be at least 8 characters."),
    confirmPassword: z.string().min(8, "Please confirm the new password."),
  })
  .refine((value) => value.newPassword === value.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });

type LoginValues = z.infer<typeof loginSchema>;
type ChangePasswordValues = z.infer<typeof changePasswordSchema>;

type ChangeRequiredState = {
  username: string;
  password: string;
  message: string;
};

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      {children}
      {error ? <span className="text-sm text-rose-700">{error}</span> : null}
    </label>
  );
}

export function LoginScreen() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const autoLoginAttemptRef = useRef<string | null>(null);
  const [changeRequired, setChangeRequired] =
    useState<ChangeRequiredState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loginForm = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      username: "",
      password: "",
    },
  });

  const changePasswordForm = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: {
      newPassword: "",
      confirmPassword: "",
    },
  });

  const loginMutation = useMutation({
    mutationFn: (values: LoginValues) =>
      apiRequest<{ profile: unknown }>("/api/auth/login", {
        method: "POST",
        body: values,
      }),
    onSuccess: () => {
      router.push("/dashboard");
      router.refresh();
    },
    onError: (error, values) => {
      if (error instanceof ApiError) {
        const payload = (
          error.data && typeof error.data === "object" ? error.data : null
        ) as {
          requires_password_change?: boolean;
          message?: string;
        } | null;

        if (payload?.requires_password_change) {
          setNotice(null);
          setChangeRequired({
            username: values.username,
            password: values.password,
            message:
              payload.message ??
              "You need to change your password before continuing.",
          });
          return;
        }
      }

      setNotice(error instanceof Error ? error.message : "Unable to sign in.");
    },
  });

  useEffect(() => {
    const username = searchParams.get("username")?.trim() ?? "";
    const rawPassword = searchParams.get("password") ?? "";
    const hashSuffix = window.location.hash
      ? decodeURIComponent(window.location.hash)
      : "";
    const password =
      rawPassword && hashSuffix ? `${rawPassword}${hashSuffix}` : rawPassword;

    if (!username || !password) {
      return;
    }

    const credentialSignature = `${username}\u0000${password}`;

    if (autoLoginAttemptRef.current === credentialSignature) {
      return;
    }

    autoLoginAttemptRef.current = credentialSignature;
    loginForm.reset({ username, password });
    setChangeRequired(null);
    setNotice("Signing in automatically...");

    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.delete("username");
    nextParams.delete("password");

    const nextUrl = nextParams.size ? `${pathname}?${nextParams}` : pathname;

    router.replace(nextUrl);
    loginMutation.mutate({ username, password });
  }, [loginForm, loginMutation, pathname, router, searchParams]);

  const changePasswordMutation = useMutation({
    mutationFn: (values: ChangePasswordValues) => {
      if (!changeRequired) {
        throw new Error("Missing password change context.");
      }

      return apiRequest<{ success?: number; faultstring?: string }>(
        "/api/auth/change-password",
        {
          method: "POST",
          body: {
            username: changeRequired.username,
            password: changeRequired.password,
            new_password: values.newPassword,
          },
        },
      );
    },
    onSuccess: () => {
      setNotice(
        "Password updated. Please sign in again with the new password.",
      );
      setChangeRequired(null);
      loginForm.reset();
      changePasswordForm.reset();
    },
    onError: (error) => {
      setNotice(
        error instanceof Error
          ? error.message
          : "Unable to change the password.",
      );
    },
  });

  return (
    <section className="panel-surface rounded-[2rem] p-6 shadow-[0_28px_90px_rgba(15,23,42,0.12)] sm:p-8">
      <div className="space-y-4">
        <div className="inline-flex items-center gap-3 rounded-full border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-900">
          <ShieldCheck className="size-4" />
          Secure operator login
        </div>
        <div>
          <h2 className="text-3xl font-semibold text-slate-950">
            {changeRequired ? "Change password" : "Sign in"}
          </h2>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            {changeRequired
              ? changeRequired.message
              : "Use the credentials from the existing PortaOne environment. Access tokens are stored in secure cookies after login."}
          </p>
        </div>
      </div>

      {notice ? (
        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {notice}
        </div>
      ) : null}

      {!changeRequired ? (
        <form
          className="mt-8 space-y-5"
          onSubmit={loginForm.handleSubmit((values) => {
            setNotice(null);
            loginMutation.mutate(values);
          })}
        >
          <Field
            label="Username"
            error={loginForm.formState.errors.username?.message}
          >
            <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-teal-500">
              <UserRound className="size-4 text-slate-400" />
              <input
                autoComplete="username"
                className="w-full bg-transparent outline-none"
                placeholder="porta-support"
                {...loginForm.register("username")}
              />
            </div>
          </Field>

          <Field
            label="Password"
            error={loginForm.formState.errors.password?.message}
          >
            <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-teal-500">
              <LockKeyhole className="size-4 text-slate-400" />
              <input
                autoComplete="current-password"
                className="w-full bg-transparent outline-none"
                placeholder="••••••••"
                type="password"
                {...loginForm.register("password")}
              />
            </div>
          </Field>

          <Button
            className="w-full"
            isPending={loginMutation.isPending}
            type="submit"
          >
            Sign in to dashboard
          </Button>
        </form>
      ) : (
        <form
          className="mt-8 space-y-5"
          onSubmit={changePasswordForm.handleSubmit((values) => {
            setNotice(null);
            changePasswordMutation.mutate(values);
          })}
        >
          <Field
            label="New password"
            error={changePasswordForm.formState.errors.newPassword?.message}
          >
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-teal-500">
              <input
                autoComplete="new-password"
                className="w-full bg-transparent outline-none"
                placeholder="Choose a strong password"
                type="password"
                {...changePasswordForm.register("newPassword")}
              />
            </div>
          </Field>

          <Field
            label="Confirm password"
            error={changePasswordForm.formState.errors.confirmPassword?.message}
          >
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-teal-500">
              <input
                autoComplete="new-password"
                className="w-full bg-transparent outline-none"
                placeholder="Repeat the new password"
                type="password"
                {...changePasswordForm.register("confirmPassword")}
              />
            </div>
          </Field>

          <div className="flex flex-wrap gap-3">
            <Button isPending={changePasswordMutation.isPending} type="submit">
              Save new password
            </Button>
            <Button
              type="button"
              variant="secondary"
              onPress={() => {
                setChangeRequired(null);
                changePasswordForm.reset();
              }}
            >
              Back to login
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
