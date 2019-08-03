from pyramids import parse
import cProfile

# Prime the parser before we profile it.
parse("hi")


if __name__ == '__main__':
    cProfile.run('parse("I took  ride to the station")')
    input("Press return...")
    cProfile.run('parse("I took a ride to the station, and then I went home.")')
