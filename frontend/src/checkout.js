const checkoutUrl = "https://checkout.razorpay.com/v1/checkout.js";
const loadError = "Razorpay Checkout could not be loaded. Check your internet connection.";

export function loadCheckout() {
  if (window.Razorpay) return Promise.resolve();

  // A failed script stays in the DOM. Replace it so a retry starts a new request.
  document.querySelector('script[data-razorpay-checkout]')?.remove();

  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = checkoutUrl;
    script.async = true;
    script.dataset.razorpayCheckout = "true";
    script.onload = () => {
      if (window.Razorpay) resolve();
      else {
        script.remove();
        reject(new Error(loadError));
      }
    };
    script.onerror = () => {
      script.remove();
      reject(new Error(loadError));
    };
    document.body.appendChild(script);
  });
}

