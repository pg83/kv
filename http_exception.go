package main

import "net/http"

type HTTPException struct {
	status  int
	message string
}

func (e *HTTPException) Error() string {
	return e.message
}

func newHTTPException(status int, message string) *HTTPException {
	if message == "" {
		message = http.StatusText(status)
	}

	return &HTTPException{status: status, message: message}
}

func (e *HTTPException) write(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	writeHeader(w, e.status)

	_, _ = chaosCall2("write response", func() (int, error) {
		return w.Write([]byte(e.Error() + "\n"))
	})
}

func throwHTTP(status int, message string) {
	throw(newHTTPException(status, message))
}
