import React from 'react';
import * as LucideIcons from 'lucide-react';

export type IconName = keyof typeof LucideIcons;

export interface IconProps extends React.SVGProps<SVGSVGElement> {
  name: string;
  size?: number | string;
  color?: string;
  className?: string;
}

export const Icon: React.FC<IconProps> = ({
  name,
  size = 16,
  color,
  className = '',
  ...props
}) => {
  const pascalName = name
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('');

  const iconsDict = LucideIcons as unknown as Record<string, React.ComponentType<any>>;
  const Component = iconsDict[pascalName] || iconsDict[name] || LucideIcons.HelpCircle;

  return <Component size={size} color={color} className={`ui-icon ${className}`.trim()} {...props} />;
};

export default Icon;
