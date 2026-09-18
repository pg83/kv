package main

var chaos Chaos = NoChaos{}

type Chaos interface {
	call(string, func() error) error
}

type NoChaos struct{}

func (NoChaos) call(_ string, cb func() error) error {
	return cb()
}

func chaosCall(what string, cb func() error) error {
	return chaos.call(what, cb)
}

func chaosCall2[T any](what string, cb func() (T, error)) (T, error) {
	var value T
	var callErr error

	err := chaos.call(what, func() error {
		value, callErr = cb()

		return callErr
	})

	return value, err
}
