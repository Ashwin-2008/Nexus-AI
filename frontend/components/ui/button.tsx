import React from 'react'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  loading?: boolean
}

export function Button({
  variant = 'primary',
  size = 'default',
  loading = false,
  children,
  className = '',
  disabled,
  ...props
}: ButtonProps) {
  const variants: Record<NonNullable<ButtonProps['variant']>, string> = {
    default: 'nx-btn--primary',
    primary: 'nx-btn--primary',
    secondary: 'nx-btn--secondary',
    outline: 'nx-btn--outline',
    ghost: 'nx-btn--ghost',
    danger: 'nx-btn--danger',
  }

  const sizes: Record<NonNullable<ButtonProps['size']>, string> = {
    default: '',
    sm: 'nx-btn--sm',
    lg: 'nx-btn--lg',
    icon: 'nx-btn--icon',
  }

  return (
    <button
      className={`nx-btn ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <span className="nx-spinner" aria-hidden="true" />}
      {children}
    </button>
  )
}
