export interface ApiSuccess<T> {
  success: true;
  data: T;
  message: string;
}

export interface ApiFailure {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Array<{
      loc?: Array<string | number>;
      msg?: string;
      type?: string;
    }>;
  };
}
