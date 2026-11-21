import React from 'react'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  type?: 'text' | 'email' | 'password' | 'number' | 'search' | 'url' | 'date' | 'datetime-local'
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { type = 'text', className = '', ...props },
  ref,
) {
  return <input ref={ref} type={type} {...props} className={`nx-input ${className}`} />
})

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className = '', ...props },
  ref,
) {
  return <textarea ref={ref} {...props} className={`nx-textarea ${className}`} />
})

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className = '', children, ...props },
  ref,
) {
  return (
    <select ref={ref} {...props} className={`nx-select ${className}`}>
      {children}
    </select>
  )
})
