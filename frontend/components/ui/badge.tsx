import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary/20 text-primary hover:bg-primary/30 border border-primary/30",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive/20 text-destructive hover:bg-destructive/30 border border-destructive/30",
        outline: "text-foreground border border-border",
        success:
          "bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30",
        warning:
          "bg-orange-500/20 text-orange-400 border border-orange-500/30 hover:bg-orange-500/30",
        info: "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30",
        purple:
          "bg-purple-500/20 text-purple-400 border border-purple-500/30 hover:bg-purple-500/30",
        blue: "bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:bg-blue-500/30",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
