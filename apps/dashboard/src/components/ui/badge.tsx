import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";

const badgeVariants = cva(
  "group/badge inline-flex w-fit shrink-0 items-center justify-center gap-1.5 overflow-hidden rounded-[5px] border border-transparent px-[9px] py-1 text-xs font-medium whitespace-nowrap transition-colors duration-[180ms] [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-[var(--ink)] text-[color:var(--background)]",
        secondary: "bg-[var(--wash)] text-[color:var(--body)]",
        destructive: "bg-[var(--fail-tint)] text-[color:var(--fail)]",
        outline: "border-[color:var(--hairline)] text-[color:var(--body)]",
        ghost: "hover:bg-[var(--wash)]",
        link: "text-[color:var(--jade-deep)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props,
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  });
}

export { Badge, badgeVariants };
