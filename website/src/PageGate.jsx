import { useEffect, useRef, useState } from 'react';

// Images get this long to arrive; a slow image shouldn't hold the whole page back.
const IMAGE_TIMEOUT_MS = 4000;

const BACKGROUND_IMAGE = '/assets/ui/background.png';

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function imageLoaded(img) {
  if (img.complete) return Promise.resolve();

  return new Promise((resolve) => {
    img.addEventListener('load', resolve, { once: true });
    img.addEventListener('error', resolve, { once: true });
  });
}

// Keeps the page hidden until the font, the logos and the background have loaded, so it
// appears all at once. Meanwhile the loading animation from index.html (#boot-loader,
// outside #root) stays on screen; it is removed when the page is shown. The page is
// rendered the whole time, just invisible and not interactive, so its images load.
export default function PageGate({ children }) {
  const contentRef = useRef(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const background = new Image();
    background.src = BACKGROUND_IMAGE;
    const images = [background, ...contentRef.current.querySelectorAll('img')];

    let cancelled = false;
    Promise.race([Promise.all([document.fonts?.ready, ...images.map(imageLoaded)]), delay(IMAGE_TIMEOUT_MS)]).then(
      () => {
        if (!cancelled) setRevealed(true);
      },
    );

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const content = contentRef.current;

    if (revealed) {
      content.removeAttribute('inert');
      document.getElementById('boot-loader')?.remove();
    } else {
      content.setAttribute('inert', '');
    }
  }, [revealed]);

  return (
    <div ref={contentRef} className={revealed ? 'page-gate' : 'page-gate page-gate-hidden'}>
      {children}
    </div>
  );
}
