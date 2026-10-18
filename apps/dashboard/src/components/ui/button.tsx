import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-[7px] border border-transparent text-[13px] font-medium whitespace-nowrap transition-colors duration-[180ms] ease-[cubic-bezier(.2,.7,.2,1)] outline-none select-none focus-visible:outline-[3px] focus-visible:outline-[color:var(--wash-focus)] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--jade-deep)] text-[color:var(--background)] hover:bg-[var(--jade-press)]",
        outline:
          "border-[color:var(--hairline)] bg-[var(--background)] text-[color:var(--body)] hover:border-[color:var(--border-hover)] aria-expanded:border-[color:var(--border-hover)]",
        secondary:
          "bg-[var(--secondary-solid)] text-[color:var(--background)] hover:bg-[var(--ink)]",
        ghost:
          "text-[color:var(--body)] hover:bg-[var(--wash)] aria-expanded:bg-[var(--wash)]",
        destructive:
          "bg-[var(--fail-tint)] text-[color:var(--fail)] hover:bg-[var(--fail-tint)]",
        link: "text-[color:var(--jade-deep)] hover:bg-[var(--wash)]",
      },
      size: {
        default: "h-[34px] gap-2 px-[13px]",
        xs: "h-6 gap-1 rounded-[6px] px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1.5 rounded-[6px] px-2.5",
        lg: "h-[34px] gap-2 px-[13px]",
        icon: "size-[34px]",
        "icon-xs": "size-6 rounded-[6px] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-[6px]",
        "icon-lg": "size-[34px]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      data-variant={variant}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
