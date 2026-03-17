const requiredEnv = ["DATABASE_URL", "AUTH_SECRET", "BACKEND_API_URL"] as const;

for (const key of requiredEnv) {
  if (!process.env[key]) {
    throw new Error(`${key} is required`);
  }
}

export const appConfig = {
  databaseUrl: process.env.DATABASE_URL as string,
  authSecret: process.env.AUTH_SECRET as string,
  backendApiUrl: process.env.BACKEND_API_URL as string,
};
