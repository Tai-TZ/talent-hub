import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "tertiary" | "danger";
type Size = "sm" | "md" | "lg";

interface Shared {
  variant?: Variant;
  size?: Size;
  block?: boolean;
}

function classes({ variant = "primary", size = "md", block, loading }: Shared & { loading?: boolean }) {
  return [
    "th-button",
    `th-button--${variant}`,
    size !== "md" ? `th-button--${size}` : "",
    block ? "th-button--block" : "",
    loading ? "th-button--loading" : "",
  ]
    .filter(Boolean)
    .join(" ");
}

export function Button({
  variant,
  size,
  block,
  loading,
  className,
  disabled,
  children,
  type = "button",
  ...rest
}: Shared & { loading?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      className={[classes({ variant, size, block, loading }), className].filter(Boolean).join(" ")}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {children}
    </button>
  );
}

export function ButtonLink({
  variant,
  size,
  block,
  className,
  href,
  children,
  ...rest
}: Shared & { href: string } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  return (
    <Link href={href} className={[classes({ variant, size, block }), className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </Link>
  );
}
