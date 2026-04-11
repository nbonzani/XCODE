/**
 * PosterImage.jsx
 * Affiche le fallback immédiatement, charge l'image en arrière-plan.
 * Évite l'attente de chargement — l'image apparaît quand elle est prête.
 */

import React, { useState, useEffect } from 'react';

const PosterImage = React.memo(function PosterImage({ url, alt, type = 'movie' }) {
  const [imgSrc, setImgSrc] = useState(null); // null = fallback affiché

  useEffect(() => {
    if (!url) return;
    setImgSrc(null); // reset fallback si url change
    const img = new Image();
    img.onload  = () => setImgSrc(url);
    img.onerror = () => setImgSrc(null);
    img.src = url;
    return () => { img.onload = null; img.onerror = null; };
  }, [url]);

  const fallback = type === 'series' ? '📺' : '🎬';

  return (
    <div className="poster-image">
      {imgSrc ? (
        <img
          src={imgSrc}
          alt={alt}
          style={{
            width: '100%', height: '100%',
            objectFit: 'contain',
            objectPosition: 'center',
            display: 'block',
          }}
        />
      ) : (
        <span className="poster-image__fallback">{fallback}</span>
      )}
    </div>
  );
});

export default PosterImage;
