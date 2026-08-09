import { getApp, getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { getAnalytics, isSupported, type Analytics } from "firebase/analytics";
import { connectAuthEmulator, getAuth, type Auth } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
};

function requireFirebaseConfig(): typeof firebaseConfig {
  const missing = Object.entries(firebaseConfig)
    .filter(([key, value]) => key !== "measurementId" && !value)
    .map(([key]) => key);

  if (missing.length > 0) {
    throw new Error(`Missing Firebase web configuration: ${missing.join(", ")}`);
  }

  return firebaseConfig;
}

// Official setup pattern: https://firebase.google.com/docs/web/setup
export function getFirebaseApp(): FirebaseApp {
  return getApps().length > 0
    ? getApp()
    : initializeApp(requireFirebaseConfig());
}

export function getFirebaseAuth(): Auth {
  const auth = getAuth(getFirebaseApp());
  const emulatorUrl = process.env.NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_URL?.trim();
  if (emulatorUrl && !auth.emulatorConfig) {
    connectAuthEmulator(auth, emulatorUrl, { disableWarnings: true });
  }
  return auth;
}

export async function getFirebaseIdToken(forceRefresh = false): Promise<string | null> {
  if (typeof window === "undefined") return null;
  try {
    const user = getFirebaseAuth().currentUser;
    return user ? await user.getIdToken(forceRefresh) : null;
  } catch {
    return null;
  }
}

export async function getFirebaseAnalytics(): Promise<Analytics | null> {
  if (typeof window === "undefined" || !(await isSupported())) {
    return null;
  }

  return getAnalytics(getFirebaseApp());
}
