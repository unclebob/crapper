trait Shape {
    fn sides(&self) -> u32;

    fn draw(&self) {}
}

impl Shape for Vec<crate::Sample> {
    fn sides(&self) -> u32 {
        0
    }
}

impl Shape for [u8] {
    fn sides(&self) -> u32 {
        8
    }
}
