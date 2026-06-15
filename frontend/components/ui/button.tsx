"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow hover:bg-primary/90 hover:shadow-glow-blue active:scale-95",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90 active:scale-95",
        outline:
          "border border-input bg-transparent shadow-sm hover:bg-accent/10 hover:text-accent hover:border-accent/50 active:scale-95",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80 active:scale-95",
        ghost: "hover:bg-accent/10 hover:text-accent active:scale-95",
        link: "text-primary underline-offset-4 hover:underline",
        glow: "bg-primary text-primary-foreground shadow-glow-blue hover:shadow-[0_0_30px_hsl(239_84%_67%_/_0.6)] active:scale-95 transition-all duration-300",
        "glow-green":
          "bg-green-600 text-white shadow-glow-green hover:shadow-[0_0_30px_hsl(142_71%_45%_/_0.6)] hover:bg-green-500 active:scale-95 transition-all duration-300",
        "glow-purple":
          "bg-purple-600 text-white shadow-glow-purple hover:shadow-[0_0_30px_hsl(271_91%_65%_/_0.6)] hover:bg-purple-500 active:scale-95 transition-all duration-300",
        "glow-red":
          "bg-red-600 text-white shadow-[0_0_20px_hsl(0_84%_60%_/_0.4)] hover:shadow-[0_0_30px_hsl(0_84%_60%_/_0.6)] hover:bg-red-500 active:scale-95 transition-all duration-300",
        glass:
          "glass-card text-foreground hover:border-primary/40 active:scale-95",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-lg px-8 text-base",
        xl: "h-12 rounded-lg px-10 text-base font-semibold",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
