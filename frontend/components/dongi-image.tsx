import Image from 'next/image'

const dongiImages = {
  big: { src: '/big-dongi.png', width: 1582, height: 994 },
  classic: { src: '/dongi-classic.png', width: 994, height: 1582 },
  daray: { src: '/dongi-daray.png', width: 1582, height: 994 },
  rope: { src: '/dongi-rope.png', width: 995, height: 1581 },
} as const

export type DongiImageVariant = keyof typeof dongiImages

export default function DongiImage({
  variant,
  alt,
  className,
  priority = false,
}: {
  variant: DongiImageVariant
  alt: string
  className?: string
  priority?: boolean
}) {
  const image = dongiImages[variant]
  return (
    <Image
      src={image.src}
      alt={alt}
      width={image.width}
      height={image.height}
      className={className}
      sizes="(max-width: 520px) 100vw, 520px"
      priority={priority}
    />
  )
}
