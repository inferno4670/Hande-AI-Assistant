import sys


def main() -> None:
	# Defer heavy imports so simple commands like --help do not crash if deps missing
	from Hande_GUI import HandeGUI

	app = HandeGUI()
	app.mainloop()


if __name__ == "__main__":
	main()
