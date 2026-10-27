(() => {
  const companyDomains = {
    ADANIENT: 'adani.com',
    ADANIPORTS: 'adaniports.com',
    APOLLOHOSP: 'apollohospitals.com',
    ASIANPAINT: 'asianpaints.com',
    AXISBANK: 'axisbank.com',
    BAJFINANCE: 'bajajfinserv.in',
    BEL: 'bel-india.in',
    BHARTIARTL: 'airtel.in',
    CIPLA: 'cipla.com',
    COALINDIA: 'coalindia.in',
    DABUR: 'dabur.com',
    EICHERMOT: 'eicher.in',
    HCLTECH: 'hcltech.com',
    HDFCBANK: 'hdfcbank.com',
    HINDALCO: 'hindalco.com',
    HINDUNILVR: 'hul.co.in',
    ICICIBANK: 'icicibank.com',
    INDUSINDBK: 'indusind.com',
    INFY: 'infosys.com',
    ITC: 'itcportal.com',
    JSWSTEEL: 'jsw.in',
    KOTAKBANK: 'kotak.com',
    LT: 'larsentoubro.com',
    'M&M': 'mahindra.com',
    MARUTI: 'marutisuzuki.com',
    NESTLEIND: 'nestle.in',
    NTPC: 'ntpc.co.in',
    ONGC: 'ongcindia.com',
    POWERGRID: 'powergrid.in',
    RELIANCE: 'ril.com',
    SBIN: 'sbi.co.in',
    SUNPHARMA: 'sunpharma.com',
    TATACONSUM: 'tataconsumer.com',
    TATASTEEL: 'tatasteel.com',
    TCS: 'tcs.com',
    TECHM: 'techmahindra.com',
    TITAN: 'titancompany.in',
    ULTRACEMCO: 'ultratechcement.com',
    WIPRO: 'wipro.com',
  };

  function escapeAttribute(value) {
    return String(value ?? '').replace(/[&<>"']/g, (character) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[character]);
  }

  window.stockLogoMarkup = function stockLogoMarkup(symbol, name = '', size = 'small') {
    const safeSymbol = escapeAttribute(String(symbol || '').toUpperCase());
    const safeName = escapeAttribute(name || symbol || 'Stock');
    const domain = companyDomains[String(symbol || '').toUpperCase()];
    const initials = escapeAttribute((String(symbol || name || '?').replace(/[^a-z0-9]/gi, '').slice(0, 2) || '?').toUpperCase());
    const image = domain
      ? `<img class="stock-brand-image" src="https://www.google.com/s2/favicons?domain_url=${encodeURIComponent(`https://${domain}`)}&amp;sz=128" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.nextElementSibling.hidden=false; this.remove()">`
      : '';

    return `<span class="stock-brand stock-brand-${size}" title="${safeName}" aria-label="${safeName} (${safeSymbol})">${image}<span class="stock-brand-fallback" ${domain ? 'hidden' : ''} aria-hidden="true">${initials}</span></span>`;
  };
})();
