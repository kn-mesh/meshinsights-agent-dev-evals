import * as SelectPrimitive from "@radix-ui/react-select";
import { Children, isValidElement, type ReactElement, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "../../lib/utils";

const EMPTY_VALUE = "__mesh_empty_select_value__";

type NativeOptionProps = {
  value?: string | number;
  disabled?: boolean;
  children?: ReactNode;
};

export type SelectProps = {
  "aria-label": string;
  value: string;
  onValueChange: (value: string) => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
};

export function Select({
  "aria-label": ariaLabel,
  value,
  onValueChange,
  children,
  className,
  disabled,
}: SelectProps) {
  const options = Children.toArray(children).filter(
    (child): child is ReactElement<NativeOptionProps> =>
      isValidElement(child) && child.type === "option",
  );

  return (
    <SelectPrimitive.Root
      value={toPrimitiveValue(value)}
      onValueChange={(nextValue) => onValueChange(fromPrimitiveValue(nextValue))}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger
        aria-label={ariaLabel}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-md border bg-card px-3 text-left text-sm text-foreground outline-none transition-colors hover:bg-accent/50 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
      >
        <SelectPrimitive.Value />
        <SelectPrimitive.Icon asChild>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-[min(22rem,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-lg"
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option, index) => {
              const optionValue = String(option.props.value ?? "");
              return (
                <SelectPrimitive.Item
                  key={`${optionValue}-${index}`}
                  value={toPrimitiveValue(optionValue)}
                  disabled={option.props.disabled}
                  data-value={optionValue}
                  className="relative flex cursor-default select-none items-center rounded-sm py-2 pl-8 pr-3 text-sm outline-none data-[disabled]:pointer-events-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground data-[disabled]:opacity-50"
                >
                  <span className="absolute left-2.5 grid size-3.5 place-items-center">
                    <SelectPrimitive.ItemIndicator>
                      <Check className="size-3.5 text-primary" />
                    </SelectPrimitive.ItemIndicator>
                  </span>
                  <SelectPrimitive.ItemText>{option.props.children}</SelectPrimitive.ItemText>
                </SelectPrimitive.Item>
              );
            })}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

function toPrimitiveValue(value: string) {
  return value === "" ? EMPTY_VALUE : value;
}

function fromPrimitiveValue(value: string) {
  return value === EMPTY_VALUE ? "" : value;
}
