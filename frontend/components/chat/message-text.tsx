import React from "react";

const URL_PATTERN = /(https?:\/\/[^\s)]+)/g;

function labelFor(url: string): string {
  try {
    const { pathname } = new URL(url);
    if (pathname.startsWith("/customer/visits/book")) return "Book a time";
  } catch {
    /* fall through to the raw address */
  }
  return url;
}

/**
 * Chat text with plain URLs made tappable. Only http(s) addresses are linked
 * (never other schemes), they open in the same tab, and the booking link gets
 * a short label so long query strings don't clutter a phone-sized bubble.
 */
export function MessageText({ text, linkClassName }: { text: string; linkClassName?: string }) {
  const parts = text.split(URL_PATTERN);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <a
            key={index}
            href={part}
            className={linkClassName ?? "underline underline-offset-2 font-semibold"}
          >
            {labelFor(part)}
          </a>
        ) : (
          <React.Fragment key={index}>{part}</React.Fragment>
        ),
      )}
    </>
  );
}
