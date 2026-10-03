package demo

import "testing"

func TestPlace(t *testing.T) {
	if Place(1) != 1 || Place(-1) != 0 {
		t.Fail()
	}
}
