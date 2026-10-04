/**
 * Icon dạng React để dùng được `currentColor`.
 * - CloseIcon, ChevronDownIcon, ArrowNextIcon: SVG của Northwind University (northwind-style/northwind/icons), hình dạng giữ nguyên.
 * - BarsIcon, CircleInfoIcon, TriangleExclamationIcon, CheckIcon: Font Awesome Free 6.7.2 (CC BY 4.0,
 *   https://fontawesome.com/license/free), dùng làm dự phòng cho hành động chung mà Northwind University không có icon riêng.
 */
import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 20, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg width={size} height={size} aria-hidden="true" focusable="false" {...rest}>
      {children}
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M6 18L18 6" />
      <path d="M18 18L6 6" />
    </Svg>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M17.9202 8.17969H11.6902H6.08024C5.12024 8.17969 4.64024 9.33969 5.32024 10.0197L10.5002 15.1997C11.3302 16.0297 12.6802 16.0297 13.5102 15.1997L15.4802 13.2297L18.6902 10.0197C19.3602 9.33969 18.8802 8.17969 17.9202 8.17969Z" />
    </Svg>
  );
}

export function ArrowNextIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M15.5122 11.1559L13.5422 9.18594L10.3322 5.97594C9.65219 5.30594 8.49219 5.78594 8.49219 6.74594V12.9759V18.5859C8.49219 19.5459 9.65219 20.0259 10.3322 19.3459L15.5122 14.1659C16.3422 13.3459 16.3422 11.9859 15.5122 11.1559Z" />
    </Svg>
  );
}

export function BarsIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 448 512" fill="currentColor" {...props}>
      <path d="M0 96C0 78.3 14.3 64 32 64l384 0c17.7 0 32 14.3 32 32s-14.3 32-32 32L32 128C14.3 128 0 113.7 0 96zM0 256c0-17.7 14.3-32 32-32l384 0c17.7 0 32 14.3 32 32s-14.3 32-32 32L32 288c-17.7 0-32-14.3-32-32zM448 416c0 17.7-14.3 32-32 32L32 448c-17.7 0-32-14.3-32-32s14.3-32 32-32l384 0c17.7 0 32 14.3 32 32z" />
    </Svg>
  );
}

export function CircleInfoIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 512 512" fill="currentColor" {...props}>
      <path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM216 336l24 0 0-64-24 0c-13.3 0-24-10.7-24-24s10.7-24 24-24l48 0c13.3 0 24 10.7 24 24l0 88 8 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-80 0c-13.3 0-24-10.7-24-24s10.7-24 24-24zm40-208a32 32 0 1 1 0 64 32 32 0 1 1 0-64z" />
    </Svg>
  );
}

export function TriangleExclamationIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 512 512" fill="currentColor" {...props}>
      <path d="M256 32c14.2 0 27.3 7.5 34.5 19.8l216 368c7.3 12.4 7.3 27.7 .2 40.1S486.3 480 472 480L40 480c-14.3 0-27.6-7.7-34.7-20.1s-7-27.8 .2-40.1l216-368C228.7 39.5 241.8 32 256 32zm0 128c-13.3 0-24 10.7-24 24l0 112c0 13.3 10.7 24 24 24s24-10.7 24-24l0-112c0-13.3-10.7-24-24-24zm32 224a32 32 0 1 0 -64 0 32 32 0 1 0 64 0z" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 448 512" fill="currentColor" {...props}>
      <path d="M438.6 105.4c12.5 12.5 12.5 32.8 0 45.3l-256 256c-12.5 12.5-32.8 12.5-45.3 0l-128-128c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0L160 338.7 393.4 105.4c12.5-12.5 32.8-12.5 45.3 0z" />
    </Svg>
  );
}

export function EyeIcon({ off = false, ...props }: IconProps & { off?: boolean }) {
  return (
    <Svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
      {off ? <path d="M4 4l16 16" /> : null}
    </Svg>
  );
}
