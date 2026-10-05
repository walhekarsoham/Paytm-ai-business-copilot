import type { ReactNode } from 'react'

type PageHeadingProps = {
  eyebrow?: string
  title: string
  description: string
  action?: ReactNode
}

export function PageHeading({ eyebrow = 'MERCHANT WORKSPACE', title, description, action }: PageHeadingProps) {
  return (
    <section className="page-heading-row">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="page-heading-action">{action}</div>}
    </section>
  )
}
