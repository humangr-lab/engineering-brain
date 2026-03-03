import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "@radix-ui/react-slot";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center justify-center rounded-full border border-transparent px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 [&>svg]:pointer-events-none transition-[color,box-shadow] overflow-hidden",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--color-accent)] text-[var(--color-text-inverse)] [a&]:hover:bg-[var(--color-accent-hover)]",
        secondary:
          "bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] [a&]:hover:bg-[var(--color-surface-3)]",
        destructive:
          "bg-[var(--color-destructive)] text-white [a&]:hover:bg-[var(--color-destructive)]/90",
        outline:
          "border-[var(--color-border-default)] text-[var(--color-text-primary)]",
        ghost:
          "[a&]:hover:bg-[var(--color-surface-2)] [a&]:hover:text-[var(--color-text-primary)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span";

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
