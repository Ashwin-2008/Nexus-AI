import React from 'react'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  type?: 'text' | 'email' | 'password' | 'number' | 'search'
}

export function Input({ type = 'text', ...props }: InputProps) {
  return <input type={type} {...props} className="rounded-md border-input px-3 py-2 text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary" />
}