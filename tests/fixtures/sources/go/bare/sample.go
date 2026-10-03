package sample

func Branchy(x int, ch chan int) int {
	if x > 0 && x < 10 {
		return 1
	}
	switch x {
	case 1, 2:
		return 2
	default:
		return 3
	}
}
