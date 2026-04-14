class Move:
    def __init__(self, start, end, piece, captured=None):
        self.start = start
        self.end = end
        self.piece = piece
        self.captured = captured

class Piece:
    def __init__(self, color):
        self.color = color

    def get_moves(self, board, x, y):
        return []

class Pawn(Piece):
    def get_moves(self, board, x, y):
        moves = []
        d = -1 if self.color == "white" else 1
        if board.is_empty(x+d, y):
            moves.append((x+d, y))
        for dy in [-1,1]:
            nx, ny = x+d, y+dy
            if board.in_bounds(nx, ny) and not board.is_empty(nx, ny):
                if board.grid[nx][ny].color != self.color:
                    moves.append((nx, ny))
        return moves

class Rook(Piece):
    def get_moves(self, board, x, y):
        return board.linear(x, y, self.color, [(1,0),(-1,0),(0,1),(0,-1)])

class Bishop(Piece):
    def get_moves(self, board, x, y):
        return board.linear(x, y, self.color, [(1,1),(1,-1),(-1,1),(-1,-1)])

class Queen(Piece):
    def get_moves(self, board, x, y):
        return board.linear(x, y, self.color,
        [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)])

class Knight(Piece):
    def get_moves(self, board, x, y):
        res=[]
        for dx,dy in [(2,1),(2,-1),(-2,1),(-2,-1),(1,2),(1,-2),(-1,2),(-1,-2)]:
            nx,ny=x+dx,y+dy
            if board.in_bounds(nx,ny):
                if board.is_empty(nx,ny) or board.grid[nx][ny].color!=self.color:
                    res.append((nx,ny))
        return res

class King(Piece):
    def get_moves(self, board, x, y):
        res=[]
        for dx in [-1,0,1]:
            for dy in [-1,0,1]:
                if dx or dy:
                    nx,ny=x+dx,y+dy
                    if board.in_bounds(nx,ny):
                        if board.is_empty(nx,ny) or board.grid[nx][ny].color!=self.color:
                            res.append((nx,ny))
        return res

class Wizard(Piece):
    def get_moves(self, board, x, y):
        return board.linear(x, y, self.color, [(2,2),(-2,-2),(2,-2),(-2,2)])

class Archer(Piece):
    def get_moves(self, board, x, y):
        res=[]
        for dx,dy in [(2,0),(-2,0),(0,2),(0,-2)]:
            nx,ny=x+dx,y+dy
            if board.in_bounds(nx,ny):
                if board.is_empty(nx,ny) or board.grid[nx][ny].color!=self.color:
                    res.append((nx,ny))
        return res

class Guard(Piece):
    def get_moves(self, board, x, y):
        return board.linear(x, y, self.color, [(1,1),(1,-1),(-1,1),(-1,-1)])

class Board:
    def __init__(self):
        self.grid=[[None]*8 for _ in range(8)]
        self.history=[]
        self.setup()

    def setup(self):
        for i in range(8):
            self.grid[6][i]=Pawn("white")
            self.grid[1][i]=Pawn("black")
        order=[Rook,Knight,Bishop,Queen,King,Bishop,Knight,Rook]
        for i,c in enumerate(order):
            self.grid[7][i]=c("white")
            self.grid[0][i]=c("black")

    def in_bounds(self,x,y):
        return 0<=x<8 and 0<=y<8

    def is_empty(self,x,y):
        return self.in_bounds(x,y) and self.grid[x][y] is None

    def linear(self,x,y,color,dirs):
        res=[]
        for dx,dy in dirs:
            nx,ny=x+dx,y+dy
            while self.in_bounds(nx,ny):
                if self.is_empty(nx,ny):
                    res.append((nx,ny))
                else:
                    if self.grid[nx][ny].color!=color:
                        res.append((nx,ny))
                    break
                nx+=dx; ny+=dy
        return res

    def move(self,x1,y1,x2,y2):
        p=self.grid[x1][y1]
        if not p: return False
        if (x2,y2) not in p.get_moves(self,x1,y1):
            return False
        cap=self.grid[x2][y2]
        self.history.append(Move((x1,y1),(x2,y2),p,cap))
        self.grid[x2][y2]=p
        self.grid[x1][y1]=None
        return True

    def undo(self):
        if not self.history: return
        m=self.history.pop()
        x1,y1=m.start; x2,y2=m.end
        self.grid[x1][y1]=m.piece
        self.grid[x2][y2]=m.captured

    def all_moves(self,color):
        res=[]
        for i in range(8):
            for j in range(8):
                p=self.grid[i][j]
                if p and p.color==color:
                    res+=p.get_moves(self,i,j)
        return res

    def print_board(self):
        for i,row in enumerate(self.grid):
            line=[]
            for j,p in enumerate(row):
                if p: line.append(self.sym(p))
                else: line.append(".")
            print(" ".join(line))
        print()

    def sym(self,p):
        m={Pawn:"P",Rook:"R",Knight:"N",Bishop:"B",Queen:"Q",King:"K",Wizard:"W",Archer:"A",Guard:"G"}
        s=m[type(p)]
        return s.lower() if p.color=="black" else s

class Game:
    def __init__(self):
        self.board=Board()
        self.turn="white"

    def show_moves(self,x,y):
        p=self.board.grid[x][y]
        if not p: return
        print(p.get_moves(self.board,x,y))

    def play(self):
        while True:
            self.board.print_board()
            cmd=input(self.turn+" move: ")
            if cmd=="undo":
                self.board.undo()
                self.turn="black" if self.turn=="white" else "white"
                continue
            if cmd.startswith("show"):
                _,x,y=cmd.split()
                self.show_moves(int(x),int(y))
                continue
            try:
                x1,y1,x2,y2=map(int,cmd.split())
            except:
                continue
            if self.board.move(x1,y1,x2,y2):
                self.turn="black" if self.turn=="white" else "white"

if __name__=="__main__":
    Game().play()
