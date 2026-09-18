package main

import "net/http"

type HTTPException struct {
	status  int
	message string
}

func (e *HTTPException) error() string {
	return e.message
}

func (e *HTTPException) Error() string {
	return e.error()
}

func newHTTPException(status int, message string) *HTTPException {
	if message == "" {
		message = http.StatusText(status)
	}

	return &HTTPException{status: status, message: message}
}

func (e *HTTPException) write(w http.ResponseWriter) {
	http.Error(w, e.message, e.status)
}

func throwHTTP(status int, message string) {
	throw(newHTTPException(status, message))
}
