/**
 * WalletPress — Self-Hosted Web3 WordPress Plugin
 * Frontend: wallet connect, token gating, crypto payments
 *
 * Trust: All wallet operations happen client-side. Private keys
 * NEVER leave the browser unless you explicitly sync them to your
 * self-hosted backend (encrypted with your passphrase).
 *
 * Compatible with: MetaMask, Phantom, and any EIP-1193 provider.
 * No external SDKs required — uses native browser APIs only.
 */

const walletpress = (() => {
  const state = {
    provider: null,
    address: null,
    chain: null,
    connected: false,
  };

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  function log(...args) {
    if (window.walletpress?.debug) console.log('[WalletPress]', ...args);
  }

  // ─── API ──────────────────────────────────────────────────────────────────

  async function api(method, endpoint, body) {
    const url = `${window.walletpress?.rest || '/wp-json/walletpress/v1'}${endpoint}`;
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json', 'X-WP-Nonce': window.walletpress?.nonce || '' },
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    return res.json();
  }

  // ─── Wallet Detection ──────────────────────────────────────────────────────

  function hasMetaMask() {
    return typeof window.ethereum !== 'undefined' && window.ethereum.isMetaMask;
  }

  function hasPhantom() {
    return typeof window.solana !== 'undefined' && window.solana.isPhantom;
  }

  function hasWalletConnect() {
    return typeof window.ethereum !== 'undefined';
  }

  // ─── Encoding helpers (no Buffer dependency) ──────────────────────────────

  function hexEncode(bytes) {
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function base58Encode(bytes) {
    const ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
    let num = BigInt('0x' + hexEncode(bytes));
    let result = '';
    while (num > 0) {
      result = ALPHABET[num % 58n] + result;
      num /= 58n;
    }
    return result || ALPHABET[0];
  }

  // ─── MetaMask ──────────────────────────────────────────────────────────────

  async function connectMetaMask() {
    if (!hasMetaMask()) {
      window.open('https://metamask.io/download', '_blank');
      throw new Error('MetaMask not installed');
    }
    const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
    const chainId = await window.ethereum.request({ method: 'eth_chainId' });
    state.provider = 'metamask';
    state.address = accounts[0];
    state.chain = chainIdToName(chainId);
    state.connected = true;
    log('MetaMask connected', state.address, state.chain);
    return state;
  }

  function chainIdToName(chainId) {
    const map = {
      '0x1': 'ethereum', '0x5': 'ethereum',
      '0x89': 'polygon', '0x38': 'bsc',
      '0x2105': 'base', '0xa': 'optimism',
      '0xa4b1': 'arbitrum', '0xa86a': 'avalanche',
    };
    return map[chainId?.toLowerCase()] || 'ethereum';
  }

  async function signMessageMetaMask(message) {
    if (!state.address) throw new Error('Not connected');
    const signature = await window.ethereum.request({
      method: 'personal_sign',
      params: [message, state.address],
    });
    return signature;
  }

  // ─── Phantom ──────────────────────────────────────────────────────────────

  async function connectPhantom() {
    if (!hasPhantom()) {
      window.open('https://phantom.app/download', '_blank');
      throw new Error('Phantom not installed');
    }
    try {
      const resp = await window.solana.connect();
      state.provider = 'phantom';
      state.address = resp.publicKey.toString();
      state.chain = 'solana';
      state.connected = true;
      log('Phantom connected', state.address);
      return state;
    } catch (e) {
      throw new Error('Phantom connection rejected');
    }
  }

  async function signMessagePhantom(message) {
    if (!state.address || !window.solana) throw new Error('Not connected');
    const encoded = new TextEncoder().encode(message);
    const signed = await window.solana.signMessage(encoded, 'utf8');

    // Browser-compatible bytes-to-hex (no Buffer dependency)
    let signature;
    if (signed.signature instanceof Uint8Array) {
      signature = hexEncode(signed.signature);
    } else if (typeof signed.signature === 'string') {
      signature = signed.signature;
    } else {
      signature = hexEncode(new Uint8Array(signed.signature));
    }
    return signature;
  }

  // ─── Auth Flow ────────────────────────────────────────────────────────────

  async function getNonce() {
    const data = await api('GET', '/auth/nonce');
    if (!data?.nonce) throw new Error('Failed to get nonce');
    return data;
  }

  async function authenticate(provider) {
    try {
      let address, signature, message, nonceHash, chain;

      const nonceData = await getNonce();
      const nonce = nonceData.nonce;
      nonceHash = nonceData.hash;

      if (provider === 'metamask') {
        const conn = await connectMetaMask();
        address = conn.address;
        chain = conn.chain;
        message = `WalletPress Login\n\nAddress: ${address}\nNonce: ${nonce}\nChain: ${chain}\n\nThis signature does not cost gas.`;
        signature = await signMessageMetaMask(message);
      } else if (provider === 'phantom') {
        const conn = await connectPhantom();
        address = conn.address;
        chain = conn.chain;
        message = `WalletPress Login\n\nAddress: ${address}\nNonce: ${nonce}\nChain: ${chain}\n\nThis signature does not cost gas.`;
        signature = await signMessagePhantom(message);
      } else if (provider === 'walletconnect') {
        window.open('https://walletconnect.com/explorer', '_blank');
        throw new Error('WalletConnect: scan QR with your wallet app');
      } else {
        throw new Error('Unsupported wallet provider');
      }

      const result = await api('POST', '/auth/verify', {
        address, signature, message, chain, nonce_hash: nonceHash,
      });

      if (result?.success) {
        window.location.reload();
      } else {
        throw new Error(result?.error || 'Authentication failed');
      }
    } catch (e) {
      log('Auth error:', e);
      showError(e.message);
    }
  }

  // ─── Token Gating ─────────────────────────────────────────────────────────

  async function verifyOwnership(tokenAddress, chain, minAmount = 1) {
    const user = window.walletpress?.user;
    if (!user?.wallet) return false;
    try {
      const result = await api('POST', '/verify-ownership', {
        address: user.wallet,
        contract: tokenAddress,
        chain: chain || user.chain || 'solana',
        min_amount: minAmount,
      });
      return result?.owns === true;
    } catch {
      return false;
    }
  }

  function setupGates() {
    for (const gate of $$('[data-wallet-gate]')) {
      const token = gate.dataset.token;
      const chain = gate.dataset.chain;
      const min = parseFloat(gate.dataset.min || '1');
      const fallback = gate.querySelector('[data-gate-fallback]');

      verifyOwnership(token, chain, min).then((owns) => {
        const content = gate.querySelector('[data-gate-content]');
        if (owns) {
          content?.classList.remove('hidden');
          fallback?.classList.add('hidden');
        } else {
          content?.classList.add('hidden');
          fallback?.classList.remove('hidden');
        }
      });
    }
  }

  // ─── Payments ────────────────────────────────────────────────────────────

  async function submitPayment(amount, token, chain, to, product, successUrl) {
    try {
      let provider = state.provider;
      if (!state.connected) {
        if (hasPhantom()) {
          await connectPhantom();
          provider = 'phantom';
        } else if (hasMetaMask()) {
          await connectMetaMask();
          provider = 'metamask';
        } else {
          throw new Error('No wallet detected. Install Phantom or MetaMask.');
        }
      }

      const from = state.address;
      const createResult = await api('POST', '/payments/create', {
        from, to, amount, token, chain,
      });

      let txHash;
      if (chain === 'solana' && provider === 'phantom') {
        txHash = await sendSolanaPayment(from, to, amount);
      } else if (provider === 'metamask') {
        txHash = await sendEVMPayment(to, amount);
      } else {
        throw new Error(`Unsupported chain/wallet: ${chain}/${provider}`);
      }

      const verifyResult = await api('POST', '/payments/verify', {
        tx_hash: txHash, chain, product,
      });

      if (verifyResult?.unlocked || verifyResult?.confirmed) {
        if (successUrl) window.location.href = successUrl;
        showSuccess('Payment confirmed!');
      } else {
        showStatus('Payment sent. Waiting for confirmation...');
      }

      return { txHash, verifyResult };
    } catch (e) {
      log('Payment error:', e);
      showError(e.message);
    }
  }

  async function sendSolanaPayment(from, to, amount) {
    if (!window.solana) throw new Error('Phantom not available');
    const { solana } = window;

    const { SystemProgram, Transaction, PublicKey, LAMPORTS_PER_SOL } = solana;
    const connection = new solana.Connection('https://api.mainnet-beta.solana.com');

    const transaction = new Transaction().add(
      SystemProgram.transfer({
        fromPubkey: new PublicKey(from),
        toPubkey: new PublicKey(to),
        lamports: Math.round(parseFloat(amount) * LAMPORTS_PER_SOL),
      })
    );
    const { signature } = await solana.signAndSendTransaction(transaction);
    return signature;
  }

  async function sendEVMPayment(to, amount) {
    if (!window.ethereum) throw new Error('MetaMask not available');
    const wei = '0x' + (BigInt(Math.round(parseFloat(amount) * 1e18))).toString(16);
    const txHash = await window.ethereum.request({
      method: 'eth_sendTransaction',
      params: [{ to, value: wei }],
    });
    return txHash;
  }

  // ─── UI ──────────────────────────────────────────────────────────────────

  function showError(msg) {
    for (const el of $$('.walletpress-error')) {
      el.textContent = msg;
      el.style.display = 'block';
      setTimeout(() => { el.style.display = 'none'; }, 5000);
    }
  }

  function showSuccess(msg) {
    for (const el of $$('.walletpress-status')) {
      el.textContent = msg;
      el.className = 'walletpress-status walletpress-success';
      el.style.display = 'block';
    }
  }

  function showStatus(msg) {
    for (const el of $$('.walletpress-status')) {
      el.textContent = msg;
      el.className = 'walletpress-status';
      el.style.display = 'block';
    }
  }

  // ─── Event Binding ────────────────────────────────────────────────────────

  function bindConnectButtons() {
    for (const btn of $$('.walletpress-btn-metamask')) {
      btn.addEventListener('click', () => authenticate('metamask'));
    }
    for (const btn of $$('.walletpress-btn-phantom')) {
      btn.addEventListener('click', () => authenticate('phantom'));
    }
    for (const btn of $$('.walletpress-btn-walletconnect')) {
      btn.addEventListener('click', () => authenticate('walletconnect'));
    }
  }

  function bindPaymentButtons() {
    for (const container of $$('.walletpress-payment')) {
      const btn = container.querySelector('.walletpress-btn-pay');
      if (!btn) continue;
      btn.addEventListener('click', () => {
        submitPayment(
          container.dataset.amount, container.dataset.token,
          container.dataset.chain, container.dataset.to,
          container.dataset.product, container.dataset.success,
        );
      });
    }
  }

  function bindDisconnect() {
    for (const btn of $$('.walletpress-disconnect')) {
      btn.addEventListener('click', async () => {
        const form = new FormData();
        form.append('action', 'walletpress_disconnect');
        form.append('nonce', window.walletpress?.nonce || '');
        try {
          await fetch(window.walletpress?.ajax_url || '/wp-admin/admin-ajax.php', {
            method: 'POST', body: form,
          });
          window.location.reload();
        } catch {
          showError('Disconnect failed');
        }
      });
    }
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function init() {
    bindConnectButtons();
    bindPaymentButtons();
    bindDisconnect();
    setupGates();

    if (window.ethereum) {
      window.ethereum.on('accountsChanged', () => window.location.reload());
      window.ethereum.on('chainChanged', () => window.location.reload());
    }
    if (window.solana) {
      window.solana.on('disconnect', () => window.location.reload());
    }

    log('WalletPress initialized');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { connectMetaMask, connectPhantom, authenticate, verifyOwnership, submitPayment, log, state };
})();
